from __future__ import annotations

import re
import sqlite3
from typing import Any

from cwmem.core.models import (
    EntryRecord,
    EventRecord,
    SearchHit,
    SearchHitExplanation,
    SearchQuery,
    StatsResult,
    ValidationIssue,
    ValidationResult,
)

_REQUIRED_TABLES = [
    "metadata",
    "entries",
    "entry_tags",
    "events",
    "event_tags",
    "event_resources",
    "entries_fts",
    "events_fts",
    "entities",
    "entities_fts",
]


def ensure_fts_schema(conn: sqlite3.Connection) -> None:
    """Lazily create FTS virtual tables and the entities stub if absent."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entities (
            internal_id TEXT PRIMARY KEY,
            public_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            aliases_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
            public_id UNINDEXED,
            title,
            body,
            tags,
            tokenize='unicode61 remove_diacritics 1'
        )
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
            public_id UNINDEXED,
            body,
            tags,
            tokenize='unicode61 remove_diacritics 1'
        )
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
            public_id UNINDEXED,
            name,
            aliases,
            tokenize='unicode61 remove_diacritics 1'
        )
        """
    )


def rebuild_fts(conn: sqlite3.Connection) -> tuple[int, int]:
    """Rebuild all FTS tables from canonical tables. Returns (entry_count, event_count)."""
    conn.execute("DELETE FROM entries_fts")
    conn.execute("DELETE FROM events_fts")
    conn.execute("DELETE FROM entities_fts")

    entry_rows = conn.execute(
        "SELECT public_id, title, body, internal_id FROM entries"
    ).fetchall()
    for row in entry_rows:
        tags_str = _get_entry_tags_str(conn, row[3])
        conn.execute(
            "INSERT INTO entries_fts(public_id, title, body, tags) VALUES (?, ?, ?, ?)",
            (row[0], row[1], row[2], tags_str),
        )

    event_rows = conn.execute(
        "SELECT public_id, body, internal_id FROM events"
    ).fetchall()
    for row in event_rows:
        tags_str = _get_event_tags_str(conn, row[2])
        conn.execute(
            "INSERT INTO events_fts(public_id, body, tags) VALUES (?, ?, ?)",
            (row[0], row[1], tags_str),
        )

    return len(entry_rows), len(event_rows)


def upsert_entry_fts(conn: sqlite3.Connection, record: EntryRecord) -> None:
    """Upsert an entry's searchable text into entries_fts."""
    conn.execute("DELETE FROM entries_fts WHERE public_id = ?", (record.public_id,))
    tags_str = " ".join(record.tags)
    conn.execute(
        "INSERT INTO entries_fts(public_id, title, body, tags) VALUES (?, ?, ?, ?)",
        (record.public_id, record.title, record.body, tags_str),
    )


def upsert_event_fts(conn: sqlite3.Connection, record: EventRecord) -> None:
    """Upsert an event's searchable text into events_fts."""
    conn.execute("DELETE FROM events_fts WHERE public_id = ?", (record.public_id,))
    tags_str = " ".join(record.tags)
    conn.execute(
        "INSERT INTO events_fts(public_id, body, tags) VALUES (?, ?, ?)",
        (record.public_id, record.body, tags_str),
    )


def search_lexical(conn: sqlite3.Connection, query: SearchQuery) -> list[SearchHit]:
    """Execute an FTS5 lexical search with deterministic filters."""
    hits: list[SearchHit] = []
    rank = 0
    match_query = _normalize_match_query(query.q)

    # --- entries ---
    entry_sql: list[str] = [
        "SELECT f.public_id, bm25(entries_fts) AS score",
        "FROM entries_fts f",
        "JOIN entries e ON e.public_id = f.public_id",
        "WHERE entries_fts MATCH ?",
    ]
    entry_params: list[Any] = [match_query]

    if query.tag:
        entry_sql.append(
            "AND EXISTS ("
            "SELECT 1 FROM entry_tags t"
            " JOIN entries e2 ON t.entry_internal_id = e2.internal_id"
            " WHERE e2.public_id = f.public_id AND t.tag = ?"
            ")"
        )
        entry_params.append(query.tag)
    if query.type:
        entry_sql.append("AND e.type = ?")
        entry_params.append(query.type)
    if query.author:
        entry_sql.append("AND e.author = ?")
        entry_params.append(query.author)
    if query.date_from:
        entry_sql.append("AND e.created_at >= ?")
        entry_params.append(query.date_from)
    if query.date_to:
        entry_sql.append("AND e.created_at <= ?")
        entry_params.append(query.date_to)

    entry_sql.append("ORDER BY score LIMIT ?")
    entry_params.append(query.limit)

    try:
        rows = conn.execute(" ".join(entry_sql), entry_params).fetchall()
    except sqlite3.OperationalError:
        rows = []

    for row in rows:
        rank += 1
        hits.append(
            SearchHit(
                resource_id=row[0],
                resource_type="entry",
                score=abs(float(row[1])),
                match_modes=["lexical"],
                explanation=SearchHitExplanation(
                    lexical_rank=rank,
                    matched_fields=["title", "body", "tags"],
                ),
            )
        )

    # --- events (skip if type/author filter was requested, as events don't have those) ---
    if not query.type and not query.author and len(hits) < query.limit:
        event_sql: list[str] = [
            "SELECT f.public_id, bm25(events_fts) AS score",
            "FROM events_fts f",
            "JOIN events e ON e.public_id = f.public_id",
            "WHERE events_fts MATCH ?",
        ]
        event_params: list[Any] = [match_query]

        if query.tag:
            event_sql.append(
                "AND EXISTS ("
                "SELECT 1 FROM event_tags t"
                " JOIN events e2 ON t.event_internal_id = e2.internal_id"
                " WHERE e2.public_id = f.public_id AND t.tag = ?"
                ")"
            )
            event_params.append(query.tag)
        if query.date_from:
            event_sql.append("AND e.occurred_at >= ?")
            event_params.append(query.date_from)
        if query.date_to:
            event_sql.append("AND e.occurred_at <= ?")
            event_params.append(query.date_to)

        remaining = query.limit - len(hits)
        event_sql.append("ORDER BY score LIMIT ?")
        event_params.append(remaining)

        try:
            event_rows = conn.execute(" ".join(event_sql), event_params).fetchall()
        except sqlite3.OperationalError:
            event_rows = []

        for row in event_rows:
            rank += 1
            hits.append(
                SearchHit(
                    resource_id=row[0],
                    resource_type="event",
                    score=abs(float(row[1])),
                    match_modes=["lexical"],
                    explanation=SearchHitExplanation(
                        lexical_rank=rank,
                        matched_fields=["body", "tags"],
                    ),
                )
            )

    return hits


def get_stats(conn: sqlite3.Connection) -> StatsResult:
    """Return row counts for all primary and FTS tables."""
    entries = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    entities = _count_if_exists(conn, "entities")
    entries_fts = _count_if_exists(conn, "entries_fts")
    events_fts = _count_if_exists(conn, "events_fts")
    entities_fts = _count_if_exists(conn, "entities_fts")
    embeddings = _count_if_exists(conn, "embeddings")

    row = conn.execute(
        "SELECT value FROM metadata WHERE key = 'last_build_at'"
    ).fetchone()
    last_build_at: str | None = row[0] if row else None

    model_row = conn.execute(
        "SELECT value FROM metadata WHERE key = 'embedding_model'"
    ).fetchone()
    embedding_model: str | None = model_row[0] if model_row else None

    return StatsResult(
        entries=entries,
        events=events,
        entries_fts=entries_fts,
        events_fts=events_fts,
        entities=entities,
        entities_fts=entities_fts,
        embeddings=embeddings,
        last_build_at=last_build_at,
        embedding_model=embedding_model,
    )


def validate_fts_consistency(conn: sqlite3.Connection) -> ValidationResult:
    """Check schema presence and FTS row-count alignment."""
    issues: list[ValidationIssue] = []

    for table in _REQUIRED_TABLES:
        if not _table_exists(conn, table):
            issues.append(
                ValidationIssue(
                    code="ERR_MISSING_TABLE",
                    message=f"Required table `{table}` does not exist.",
                    details={"table": table},
                )
            )

    if issues:
        return ValidationResult(ok=False, issues=issues)

    entry_count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    fts_entry_count = conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0]
    if entry_count != fts_entry_count:
        issues.append(
            ValidationIssue(
                code="ERR_FTS_DRIFT_ENTRIES",
                message=(
                    f"entries_fts has {fts_entry_count} rows but entries has {entry_count}. "
                    "Run `cwmem build` to resync."
                ),
                details={
                    "entries_count": entry_count,
                    "entries_fts_count": fts_entry_count,
                },
            )
        )

    event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    fts_event_count = conn.execute("SELECT COUNT(*) FROM events_fts").fetchone()[0]
    if event_count != fts_event_count:
        issues.append(
            ValidationIssue(
                code="ERR_FTS_DRIFT_EVENTS",
                message=(
                    f"events_fts has {fts_event_count} rows but events has {event_count}. "
                    "Run `cwmem build` to resync."
                ),
                details={
                    "events_count": event_count,
                    "events_fts_count": fts_event_count,
                },
            )
        )

    return ValidationResult(ok=not issues, issues=issues)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = ?", (name,)
    ).fetchone()
    return row is not None


def _count_if_exists(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608


def _get_entry_tags_str(conn: sqlite3.Connection, internal_id: str) -> str:
    rows = conn.execute(
        "SELECT tag FROM entry_tags WHERE entry_internal_id = ? ORDER BY tag ASC",
        (internal_id,),
    ).fetchall()
    return " ".join(row[0] for row in rows)


def _get_event_tags_str(conn: sqlite3.Connection, internal_id: str) -> str:
    rows = conn.execute(
        "SELECT tag FROM event_tags WHERE event_internal_id = ? ORDER BY tag ASC",
        (internal_id,),
    ).fetchall()
    return " ".join(row[0] for row in rows)


def _normalize_match_query(raw: str) -> str:
    tokens = re.findall(r"\w+", raw, flags=re.UNICODE)
    if not tokens:
        return raw
    return " ".join(tokens)
