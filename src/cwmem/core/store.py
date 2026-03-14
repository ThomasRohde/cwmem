from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

import orjson

from cwmem.core import embeddings as _emb
from cwmem.core import fts as _fts
from cwmem.core.events import append_event, build_entry_lifecycle_event
from cwmem.core.fingerprints import compute_entity_fingerprint, compute_entry_fingerprint
from cwmem.core.ids import generate_internal_id, next_public_id
from cwmem.core.models import (
    CommandError,
    CreateEntryInput,
    CreateEventInput,
    EntityRecord,
    EntryRecord,
    EventRecord,
    EventResource,
    ListEntriesQuery,
    LogQuery,
    MutationResult,
    SearchHit,
    SearchQuery,
    StatsResult,
    TagMutationInput,
    UpdateEntryInput,
    ValidationResult,
)
from cwmem.output.envelope import AppError

SCHEMA_VERSION = "3"


def database_path(root: Path) -> Path:
    return root / ".cwmem" / "memory.sqlite"


def ensure_schema(root: Path) -> Path:
    path = database_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entries (
                internal_id TEXT PRIMARY KEY,
                public_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                author TEXT,
                provenance_json TEXT NOT NULL,
                related_ids_json TEXT NOT NULL,
                entity_refs_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entry_tags (
                entry_internal_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(entry_internal_id, tag),
                FOREIGN KEY(entry_internal_id) REFERENCES entries(internal_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS events (
                internal_id TEXT PRIMARY KEY,
                public_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                body TEXT NOT NULL,
                author TEXT,
                occurred_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                related_ids_json TEXT NOT NULL,
                entity_refs_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                fingerprint TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS event_tags (
                event_internal_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(event_internal_id, tag),
                FOREIGN KEY(event_internal_id) REFERENCES events(internal_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS event_resources (
                event_internal_id TEXT NOT NULL,
                resource_public_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'subject',
                PRIMARY KEY(event_internal_id, resource_public_id, role),
                FOREIGN KEY(event_internal_id) REFERENCES events(internal_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS entities (
                internal_id TEXT PRIMARY KEY,
                public_id TEXT NOT NULL UNIQUE,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                aliases_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entity_tags (
                entity_internal_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(entity_internal_id, tag),
                FOREIGN KEY(entity_internal_id) REFERENCES entities(internal_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS edges (
                internal_id TEXT PRIMARY KEY,
                public_id TEXT NOT NULL UNIQUE,
                source_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                target_type TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                provenance TEXT NOT NULL,
                confidence REAL NOT NULL,
                is_inferred INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_entries_public_id ON entries(public_id);
            CREATE INDEX IF NOT EXISTS idx_events_public_id ON events(public_id);
            CREATE INDEX IF NOT EXISTS idx_entities_public_id ON entities(public_id);
            CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON events(occurred_at, public_id);
            CREATE INDEX IF NOT EXISTS idx_event_resources_resource_public_id
                ON event_resources(resource_public_id, role);
            CREATE INDEX IF NOT EXISTS idx_entry_tags_tag ON entry_tags(tag);
            CREATE INDEX IF NOT EXISTS idx_event_tags_tag ON event_tags(tag);
            CREATE INDEX IF NOT EXISTS idx_entity_tags_tag ON entity_tags(tag);
            CREATE INDEX IF NOT EXISTS idx_edges_source_id
                ON edges(source_id, relation_type, target_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target_id
                ON edges(target_id, relation_type, source_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_edges_unique_signature
                ON edges(source_id, target_id, relation_type, is_inferred);
            """
        )
        _migrate_legacy_graph_schema(conn)
        _fts.ensure_fts_schema(conn)
        _emb.ensure_embeddings_schema(conn)
        conn.executemany(
            """
            INSERT INTO metadata(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO NOTHING
            """,
            [
                ("schema_version", SCHEMA_VERSION),
                ("next_mem_id", "1"),
                ("next_evt_id", "1"),
                ("next_ent_id", "1"),
                ("next_edg_id", "1"),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return path


def create_entry(root: Path, entry_input: CreateEntryInput) -> EntryRecord:
    conn = _connect(root)
    try:
        with conn:
            now = _utc_now()
            tags = _normalize_tags(entry_input.tags)
            _validate_entity_refs_exist(conn, entry_input.entity_refs)
            record = EntryRecord(
                internal_id=generate_internal_id(),
                public_id=next_public_id(conn, "mem"),
                title=entry_input.title,
                body=entry_input.body,
                type=entry_input.type,
                status=entry_input.status,
                author=entry_input.author,
                tags=tags,
                provenance=dict(entry_input.provenance),
                related_ids=sorted(set(entry_input.related_ids)),
                entity_refs=sorted(set(entry_input.entity_refs)),
                metadata=dict(entry_input.metadata),
                fingerprint="",
                created_at=now,
                updated_at=now,
            )
            record.fingerprint = compute_entry_fingerprint(record)
            _insert_entry(conn, record)
            _fts.upsert_entry_fts(conn, record)
            evt = append_event(
                conn,
                build_entry_lifecycle_event(record, event_type="memory.entry.created"),
            )
            _fts.upsert_event_fts(conn, evt)
            return record
    finally:
        conn.close()


def update_entry(root: Path, update_input: UpdateEntryInput) -> tuple[EntryRecord, MutationResult]:
    conn = _connect(root)
    try:
        with conn:
            existing = _get_entry_by_public_id(conn, update_input.public_id)
            if update_input.expected_fingerprint is not None and (
                update_input.expected_fingerprint != existing.fingerprint
            ):
                _raise_conflict(
                    "Entry fingerprint does not match the expected current value.",
                    details={
                        "resource_id": update_input.public_id,
                        "expected_fingerprint": update_input.expected_fingerprint,
                        "actual_fingerprint": existing.fingerprint,
                    },
                    suggested_action=(
                        "Re-run `cwmem get` to fetch the latest fingerprint, then retry the update."
                    ),
                )

            candidate = existing.model_copy(deep=True)
            if update_input.title is not None:
                candidate.title = update_input.title
            if update_input.body is not None:
                candidate.body = update_input.body
            if update_input.type is not None:
                candidate.type = update_input.type
            if update_input.status is not None:
                candidate.status = update_input.status
            if update_input.author is not None:
                candidate.author = update_input.author
            if update_input.provenance is not None:
                candidate.provenance = dict(update_input.provenance)
            if update_input.related_ids is not None:
                candidate.related_ids = sorted(set(update_input.related_ids))
            if update_input.entity_refs is not None:
                candidate.entity_refs = sorted(set(update_input.entity_refs))
            if update_input.metadata is not None:
                candidate.metadata = dict(update_input.metadata)

            _validate_entity_refs_exist(conn, candidate.entity_refs)

            changed_fields = _changed_fields(existing, candidate)
            if not changed_fields:
                return existing, MutationResult(applied=False, resource_kind="entry")

            candidate.updated_at = _utc_now()
            candidate.fingerprint = compute_entry_fingerprint(candidate)
            if update_input.expected_fingerprint is not None:
                cursor = conn.execute(
                    """
                    UPDATE entries
                    SET title = ?,
                        body = ?,
                        type = ?,
                        status = ?,
                        author = ?,
                        provenance_json = ?,
                        related_ids_json = ?,
                        entity_refs_json = ?,
                        metadata_json = ?,
                        fingerprint = ?,
                        updated_at = ?
                    WHERE internal_id = ? AND fingerprint = ?
                    """,
                    (
                        candidate.title,
                        candidate.body,
                        candidate.type,
                        candidate.status,
                        candidate.author,
                        _json_dump(candidate.provenance),
                        _json_dump(candidate.related_ids),
                        _json_dump(candidate.entity_refs),
                        _json_dump(candidate.metadata),
                        candidate.fingerprint,
                        candidate.updated_at,
                        candidate.internal_id,
                        existing.fingerprint,
                    ),
                )
                if cursor.rowcount == 0:
                    _raise_conflict(
                        "Entry fingerprint does not match the expected current value.",
                        details={
                            "resource_id": update_input.public_id,
                            "expected_fingerprint": update_input.expected_fingerprint,
                            "actual_fingerprint": existing.fingerprint,
                        },
                        suggested_action=(
                            "Re-run `cwmem get` to fetch the latest fingerprint, "
                            "then retry the update."
                        ),
                    )
            else:
                conn.execute(
                    """
                    UPDATE entries
                    SET title = ?,
                        body = ?,
                        type = ?,
                        status = ?,
                        author = ?,
                        provenance_json = ?,
                        related_ids_json = ?,
                        entity_refs_json = ?,
                        metadata_json = ?,
                        fingerprint = ?,
                        updated_at = ?
                    WHERE internal_id = ?
                    """,
                    (
                        candidate.title,
                        candidate.body,
                        candidate.type,
                        candidate.status,
                        candidate.author,
                        _json_dump(candidate.provenance),
                        _json_dump(candidate.related_ids),
                        _json_dump(candidate.entity_refs),
                        _json_dump(candidate.metadata),
                        candidate.fingerprint,
                        candidate.updated_at,
                        candidate.internal_id,
                    ),
                )
            _fts.upsert_entry_fts(conn, candidate)
            evt = append_event(
                conn,
                build_entry_lifecycle_event(
                    candidate,
                    event_type="memory.entry.updated",
                    previous_fingerprint=existing.fingerprint,
                    changed_fields=changed_fields,
                ),
            )
            _fts.upsert_event_fts(conn, evt)
            return candidate, MutationResult(applied=True, resource_kind="entry")
    finally:
        conn.close()


def get_entry(root: Path, public_id: str) -> EntryRecord:
    conn = _connect(root)
    try:
        return _get_entry_by_public_id(conn, public_id)
    finally:
        conn.close()


def list_entries(root: Path, query: ListEntriesQuery) -> list[EntryRecord]:
    conn = _connect(root)
    try:
        sql_parts = ["SELECT e.* FROM entries e"]
        params: list[Any] = []
        where_clauses: list[str] = []
        if query.tag:
            where_clauses.append(
                """
                EXISTS (
                    SELECT 1 FROM entry_tags t
                    WHERE t.entry_internal_id = e.internal_id AND t.tag = ?
                )
                """
            )
            params.append(query.tag)
        if query.type:
            where_clauses.append("e.type = ?")
            params.append(query.type)
        if query.status:
            where_clauses.append("e.status = ?")
            params.append(query.status)
        if query.author:
            where_clauses.append("e.author = ?")
            params.append(query.author)
        if where_clauses:
            sql_parts.append("WHERE " + " AND ".join(where_clauses))
        sql_parts.append("ORDER BY e.public_id ASC LIMIT ?")
        params.append(query.limit)
        rows = conn.execute("\n".join(sql_parts), params).fetchall()
        return [_entry_from_row(conn, row) for row in rows]
    finally:
        conn.close()


def add_event(root: Path, event_input: CreateEventInput) -> EventRecord:
    conn = _connect(root)
    try:
        with conn:
            _validate_resources_exist(
                conn,
                [resource.resource_id for resource in event_input.resources],
            )
            _validate_entity_refs_exist(conn, event_input.entity_refs)
            record = append_event(conn, event_input)
            _fts.upsert_event_fts(conn, record)
            return record
    finally:
        conn.close()


def list_events(root: Path, query: LogQuery) -> list[EventRecord]:
    conn = _connect(root)
    try:
        if query.resource:
            _validate_resources_exist(conn, [query.resource])

        sql = ["SELECT DISTINCT e.* FROM events e"]
        params: list[Any] = []
        where_clauses: list[str] = []

        if query.resource:
            sql.append("JOIN event_resources er ON er.event_internal_id = e.internal_id")
            where_clauses.append("er.resource_public_id = ?")
            params.append(query.resource)
        if query.tag:
            where_clauses.append(
                """
                EXISTS (
                    SELECT 1 FROM event_tags t
                    WHERE t.event_internal_id = e.internal_id AND t.tag = ?
                )
                """
            )
            params.append(query.tag)
        if query.event_type:
            where_clauses.append("e.event_type = ?")
            params.append(query.event_type)

        if where_clauses:
            sql.append("WHERE " + " AND ".join(where_clauses))
        sql.append("ORDER BY e.occurred_at ASC, e.public_id ASC LIMIT ?")
        params.append(query.limit)

        rows = conn.execute("\n".join(sql), params).fetchall()
        return [_event_from_row(conn, row) for row in rows]
    finally:
        conn.close()


def search_entries(root: Path, query: SearchQuery) -> list[Any]:
    from cwmem.core import graph as _graph
    from cwmem.core import hybrid_search as _hybrid

    conn = _connect(root)
    try:
        if query.semantic_only:
            hits = _hybrid.search_semantic(root, conn, query)
        elif query.lexical_only:
            hits = _fts.search_lexical(conn, query)
        else:
            hits = _hybrid.search_hybrid(root, conn, query)
        if query.expand_graph:
            return _graph.expand_search_hits(conn, hits, query.limit)
        return hits
    finally:
        conn.close()


def search(root: Path, query: SearchQuery) -> list[SearchHit]:
    from cwmem.core import graph as _graph
    from cwmem.core import hybrid_search as _hybrid

    conn = _connect(root)
    try:
        if query.semantic_only:
            hits = _hybrid.search_semantic(root, conn, query)
        elif query.lexical_only:
            hits = _fts.search_lexical(conn, query)
        else:
            hits = _hybrid.search_hybrid(root, conn, query)
        if query.expand_graph:
            return _graph.expand_search_hits(conn, hits, query.limit)
        return hits
    finally:
        conn.close()


def get_fts_stats(root: Path) -> StatsResult:
    conn = _connect(root)
    try:
        return _fts.get_stats(conn)
    finally:
        conn.close()


def validate_fts(root: Path) -> ValidationResult:
    conn = _connect(root)
    try:
        base = _fts.validate_fts_consistency(conn)
        embedding_issues = _emb.validate_embeddings_consistency(root, conn)
        if not embedding_issues:
            return base
        return ValidationResult(ok=False, issues=[*base.issues, *embedding_issues])
    finally:
        conn.close()


def rebuild_fts_index(root: Path) -> tuple[int, int, int]:
    """Rebuild FTS indexes and embeddings. Returns (entry_count, event_count, embedding_count)."""
    from cwmem.core import graph as _graph

    conn = _connect(root)
    try:
        with conn:
            _graph.rebuild_inferred_edges(conn)
            entry_count, event_count = _fts.rebuild_fts(conn)
            embedding_count = _emb.rebuild_embeddings(root, conn)
            now = _utc_now()
            conn.execute(
                """
                INSERT INTO metadata(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("last_build_at", now),
            )
        return entry_count, event_count, embedding_count
    finally:
        conn.close()


def add_tags(
    root: Path, mutation: TagMutationInput
) -> tuple[EntryRecord | EventRecord, MutationResult]:
    return _mutate_tags(root, mutation, add=True)


def remove_tags(
    root: Path, mutation: TagMutationInput
) -> tuple[EntryRecord | EventRecord, MutationResult]:
    return _mutate_tags(root, mutation, add=False)


def get_stats(root: Path) -> StatsResult:
    conn = _connect(root)
    try:
        return _fts.get_stats(conn)
    finally:
        conn.close()


def rebuild_index(root: Path) -> tuple[int, int, int]:
    """Rebuild FTS indexes and embeddings. Returns (entry_count, event_count, embedding_count)."""
    from cwmem.core import graph as _graph

    conn = _connect(root)
    try:
        with conn:
            _graph.rebuild_inferred_edges(conn)
            counts = _fts.rebuild_fts(conn)
            embedding_count = _emb.rebuild_embeddings(root, conn)
            now = _utc_now()
            conn.execute(
                "INSERT INTO metadata(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("last_build_at", now),
            )
        return counts[0], counts[1], embedding_count
    finally:
        conn.close()


def validate_index(root: Path) -> ValidationResult:
    conn = _connect(root)
    try:
        base = _fts.validate_fts_consistency(conn)
        embedding_issues = _emb.validate_embeddings_consistency(root, conn)
        if not embedding_issues:
            return base
        return ValidationResult(ok=False, issues=[*base.issues, *embedding_issues])
    finally:
        conn.close()


def _mutate_tags(
    root: Path, mutation: TagMutationInput, *, add: bool
) -> tuple[EntryRecord | EventRecord, MutationResult]:
    conn = _connect(root)
    try:
        with conn:
            resource_kind = _resource_kind(mutation.resource_id)
            tags = _normalize_tags(mutation.tags)
            applied = False
            timestamp = _utc_now()
            if resource_kind == "entry":
                record = _get_entry_by_public_id(conn, mutation.resource_id)
                if add:
                    for tag in tags:
                        cursor = conn.execute(
                            """
                            INSERT OR IGNORE INTO entry_tags(entry_internal_id, tag, created_at)
                            VALUES (?, ?, ?)
                            """,
                            (record.internal_id, tag, timestamp),
                        )
                        applied = applied or cursor.rowcount > 0
                else:
                    cursor = conn.executemany(
                        "DELETE FROM entry_tags WHERE entry_internal_id = ? AND tag = ?",
                        [(record.internal_id, tag) for tag in tags],
                    )
                    applied = cursor.rowcount > 0
                refreshed = _get_entry_by_public_id(conn, mutation.resource_id)
                if applied:
                    refreshed.updated_at = timestamp
                    refreshed.fingerprint = compute_entry_fingerprint(refreshed)
                    conn.execute(
                        "UPDATE entries SET fingerprint = ?, updated_at = ? WHERE internal_id = ?",
                        (refreshed.fingerprint, refreshed.updated_at, refreshed.internal_id),
                    )
                    _fts.upsert_entry_fts(conn, refreshed)
                    evt = append_event(
                        conn,
                        build_entry_lifecycle_event(
                            refreshed,
                            event_type="memory.entry.updated",
                            previous_fingerprint=record.fingerprint,
                            changed_fields=["tags"],
                        ),
                    )
                    _fts.upsert_event_fts(conn, evt)
                return (
                    refreshed,
                    MutationResult(applied=applied, resource_kind="entry"),
                )

            _raise_validation(
                "Event records are append-only and cannot be retagged after creation.",
                details={"resource_id": mutation.resource_id},
                suggested_action=(
                    "Supply event tags during `cwmem event-add`, or create a new event."
                ),
            )
            raise AssertionError("unreachable")
    finally:
        conn.close()


def _connect(root: Path) -> sqlite3.Connection:
    path = database_path(root)
    if not path.exists():
        _raise_validation(
            "The runtime database does not exist for this repository.",
            details={"database_path": path.as_posix()},
            suggested_action="Run `cwmem init` in the repository root, then retry the command.",
        )
    ensure_schema(root)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _fts.ensure_fts_schema(conn)
    _emb.ensure_embeddings_schema(conn)
    return conn


def _insert_entry(conn: sqlite3.Connection, record: EntryRecord) -> None:
    conn.execute(
        """
        INSERT INTO entries(
            internal_id,
            public_id,
            title,
            body,
            type,
            status,
            author,
            provenance_json,
            related_ids_json,
            entity_refs_json,
            metadata_json,
            fingerprint,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.internal_id,
            record.public_id,
            record.title,
            record.body,
            record.type,
            record.status,
            record.author,
            _json_dump(record.provenance),
            _json_dump(record.related_ids),
            _json_dump(record.entity_refs),
            _json_dump(record.metadata),
            record.fingerprint,
            record.created_at,
            record.updated_at,
        ),
    )
    conn.executemany(
        "INSERT OR IGNORE INTO entry_tags(entry_internal_id, tag, created_at) VALUES (?, ?, ?)",
        [(record.internal_id, tag, record.created_at) for tag in record.tags],
    )


def _get_entry_by_public_id(conn: sqlite3.Connection, public_id: str) -> EntryRecord:
    row = conn.execute("SELECT * FROM entries WHERE public_id = ?", (public_id,)).fetchone()
    if row is None:
        _raise_validation(
            "Entry not found.",
            details={"resource_id": public_id},
            suggested_action="Run `cwmem list` to inspect available entries, then retry.",
        )
    return _entry_from_row(conn, row)


def _get_event_by_public_id(conn: sqlite3.Connection, public_id: str) -> EventRecord:
    row = conn.execute("SELECT * FROM events WHERE public_id = ?", (public_id,)).fetchone()
    if row is None:
        _raise_validation(
            "Event not found.",
            details={"resource_id": public_id},
            suggested_action="Run `cwmem log` to inspect available events, then retry.",
        )
    return _event_from_row(conn, row)


def _entry_from_row(conn: sqlite3.Connection, row: sqlite3.Row) -> EntryRecord:
    tags = [
        tag_row[0]
        for tag_row in conn.execute(
            "SELECT tag FROM entry_tags WHERE entry_internal_id = ? ORDER BY tag ASC",
            (row["internal_id"],),
        ).fetchall()
    ]
    return EntryRecord(
        internal_id=row["internal_id"],
        public_id=row["public_id"],
        title=row["title"],
        body=row["body"],
        type=row["type"],
        status=row["status"],
        author=row["author"],
        tags=tags,
        provenance=_json_load(row["provenance_json"]),
        related_ids=_json_load(row["related_ids_json"]),
        entity_refs=_json_load(row["entity_refs_json"]),
        metadata=_json_load(row["metadata_json"]),
        fingerprint=row["fingerprint"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _event_from_row(conn: sqlite3.Connection, row: sqlite3.Row) -> EventRecord:
    tags = [
        tag_row[0]
        for tag_row in conn.execute(
            "SELECT tag FROM event_tags WHERE event_internal_id = ? ORDER BY tag ASC",
            (row["internal_id"],),
        ).fetchall()
    ]
    resources = [
        EventResource(resource_id=resource_row["resource_public_id"], role=resource_row["role"])
        for resource_row in conn.execute(
            """
            SELECT resource_public_id, role
            FROM event_resources
            WHERE event_internal_id = ?
            ORDER BY resource_public_id ASC, role ASC
            """,
            (row["internal_id"],),
        ).fetchall()
    ]
    return EventRecord(
        internal_id=row["internal_id"],
        public_id=row["public_id"],
        event_type=row["event_type"],
        body=row["body"],
        author=row["author"],
        tags=tags,
        resources=resources,
        related_ids=_json_load(row["related_ids_json"]),
        entity_refs=_json_load(row["entity_refs_json"]),
        metadata=_json_load(row["metadata_json"]),
        fingerprint=row["fingerprint"],
        occurred_at=row["occurred_at"],
        created_at=row["created_at"],
    )


def _entity_from_row(conn: sqlite3.Connection, row: sqlite3.Row) -> EntityRecord:
    tags = [
        tag_row[0]
        for tag_row in conn.execute(
            "SELECT tag FROM entity_tags WHERE entity_internal_id = ? ORDER BY tag ASC",
            (row["internal_id"],),
        ).fetchall()
    ]
    return EntityRecord(
        internal_id=row["internal_id"],
        public_id=row["public_id"],
        entity_type=row["entity_type"],
        name=row["name"],
        description=row["description"],
        status=row["status"],
        aliases=_json_load(row["aliases_json"]),
        tags=tags,
        provenance=_json_load(row["provenance_json"]),
        metadata=_json_load(row["metadata_json"]),
        fingerprint=row["fingerprint"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _resource_kind(resource_id: str) -> str:
    if resource_id.startswith("mem-"):
        return "entry"
    if resource_id.startswith("evt-"):
        return "event"
    if resource_id.startswith("ent-"):
        return "entity"
    _raise_validation(
        "Unsupported resource identifier.",
        details={"resource_id": resource_id},
        suggested_action=(
            "Use a public entry ID like `mem-000001`, an event ID like `evt-000001`, "
            "or an entity ID like `ent-000001`."
        ),
    )
    raise AssertionError("unreachable")


def _validate_resources_exist(conn: sqlite3.Connection, resource_ids: list[str]) -> None:
    for resource_id in resource_ids:
        resource_kind = _resource_kind(resource_id)
        if resource_kind == "entry":
            row = conn.execute(
                "SELECT 1 FROM entries WHERE public_id = ?",
                (resource_id,),
            ).fetchone()
            if row is None:
                _raise_validation(
                    "Referenced entry does not exist.",
                    details={"resource_id": resource_id},
                    suggested_action=(
                        "Create the entry first or remove the invalid resource reference."
                    ),
                )
        elif resource_kind == "event":
            row = conn.execute(
                "SELECT 1 FROM events WHERE public_id = ?",
                (resource_id,),
            ).fetchone()
            if row is None:
                _raise_validation(
                    "Referenced event does not exist.",
                    details={"resource_id": resource_id},
                    suggested_action=(
                        "Create the event first or remove the invalid resource reference."
                    ),
                )
        else:
            row = conn.execute(
                "SELECT 1 FROM entities WHERE public_id = ?",
                (resource_id,),
            ).fetchone()
            if row is None:
                _raise_validation(
                    "Referenced entity does not exist.",
                    details={"resource_id": resource_id},
                    suggested_action=(
                        "Create the entity first or remove the invalid entity reference."
                    ),
                )


def _validate_entity_refs_exist(conn: sqlite3.Connection, entity_refs: list[str]) -> None:
    if not entity_refs:
        return
    normalized_refs = sorted(set(entity_refs))
    for entity_ref in normalized_refs:
        if _resource_kind(entity_ref) != "entity":
            _raise_validation(
                "Entity references must point to entity IDs.",
                details={"resource_id": entity_ref},
                suggested_action=(
                    "Use `ent-...` identifiers in `--entity-ref`, or create the entity first."
                ),
            )
    _validate_resources_exist(conn, normalized_refs)


def _migrate_legacy_graph_schema(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "entities"):
        return

    columns = _table_columns(conn, "entities")
    migrations: list[tuple[str, str]] = [
        (
            "entity_type",
            "ALTER TABLE entities ADD COLUMN entity_type TEXT NOT NULL DEFAULT 'entity'",
        ),
        (
            "description",
            "ALTER TABLE entities ADD COLUMN description TEXT NOT NULL DEFAULT ''",
        ),
        (
            "status",
            "ALTER TABLE entities ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
        ),
        (
            "aliases_json",
            "ALTER TABLE entities ADD COLUMN aliases_json TEXT NOT NULL DEFAULT '[]'",
        ),
        (
            "provenance_json",
            "ALTER TABLE entities ADD COLUMN provenance_json TEXT NOT NULL DEFAULT '{}'",
        ),
        (
            "metadata_json",
            "ALTER TABLE entities ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'",
        ),
        (
            "fingerprint",
            "ALTER TABLE entities ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''",
        ),
    ]
    for column_name, ddl in migrations:
        if column_name not in columns:
            conn.execute(ddl)

    columns = _table_columns(conn, "entities")
    if "kind" in columns:
        conn.execute(
            """
            UPDATE entities
            SET entity_type = kind
            WHERE entity_type = 'entity'
              AND COALESCE(kind, '') != ''
            """
        )
    conn.execute(
        """
        UPDATE entities
        SET entity_type = 'entity'
        WHERE COALESCE(entity_type, '') = ''
        """
    )
    conn.execute(
        """
        UPDATE entities
        SET aliases_json = '[]'
        WHERE COALESCE(aliases_json, '') = ''
        """
    )
    conn.execute(
        """
        UPDATE entities
        SET provenance_json = '{}'
        WHERE COALESCE(provenance_json, '') = ''
        """
    )
    conn.execute(
        """
        UPDATE entities
        SET metadata_json = '{}'
        WHERE COALESCE(metadata_json, '') = ''
        """
    )
    for row in conn.execute(
        """
        SELECT *
        FROM entities
        WHERE COALESCE(fingerprint, '') = ''
        ORDER BY public_id ASC
        """
    ).fetchall():
        record = _entity_from_row(conn, row)
        conn.execute(
            "UPDATE entities SET fingerprint = ? WHERE internal_id = ?",
            (compute_entity_fingerprint(record), record.internal_id),
        )


def _json_dump(value: Any) -> str:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")


def _json_load(value: str) -> Any:
    return orjson.loads(value)


def _normalize_tags(tags: list[str]) -> list[str]:
    return sorted({tag.strip() for tag in tags if tag.strip()})


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _changed_fields(existing: EntryRecord, candidate: EntryRecord) -> list[str]:
    fields = [
        "title",
        "body",
        "type",
        "status",
        "author",
        "provenance",
        "related_ids",
        "entity_refs",
        "metadata",
    ]
    return sorted(
        field for field in fields if getattr(existing, field) != getattr(candidate, field)
    )


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()  # noqa: S608
    return {str(row[1]) for row in rows}


def _raise_validation(
    message: str, *, details: dict[str, Any] | None = None, suggested_action: str
) -> NoReturn:
    raise AppError.from_command_error(
        CommandError(
            code="ERR_VALIDATION_INPUT",
            message=message,
            retryable=False,
            suggested_action=suggested_action,
            details=details or {},
        )
    )


def _raise_conflict(
    message: str, *, details: dict[str, Any] | None = None, suggested_action: str
) -> NoReturn:
    raise AppError.from_command_error(
        CommandError(
            code="ERR_CONFLICT_STALE_FINGERPRINT",
            message=message,
            retryable=False,
            suggested_action=suggested_action,
            details=details or {},
        )
    )
