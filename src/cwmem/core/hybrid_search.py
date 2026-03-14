"""Hybrid search combining lexical (FTS5) and semantic (embedding) retrieval.

Lexical-only and semantic-only modes are also supported. Hybrid mode merges
candidates from both retrieval paths using Reciprocal Rank Fusion (RRF).

Each returned ``SearchHit`` carries a ``match_modes`` list that tells callers
which retrieval mode(s) contributed to the result, plus an ``explanation``
block with ``lexical_rank``, ``semantic_rank``, and the final ``rrf_score``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

from cwmem.core import embeddings as _emb
from cwmem.core import fts as _fts
from cwmem.core.models import SearchHit, SearchHitExplanation, SearchQuery

# RRF constant — standard value from Cormack et al. (2009)
_RRF_K = 60


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity for two 1-D float32 vectors."""
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _rrf_score(rank: int) -> float:
    return 1.0 / (_RRF_K + rank)


def search_semantic(
    root: Path,
    conn: sqlite3.Connection,
    query: SearchQuery,
) -> list[SearchHit]:
    """Return hits ranked by cosine similarity to the query embedding."""
    _emb.ensure_embeddings_schema(conn)
    embedding_count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    if embedding_count == 0:
        return []

    query_vec = _emb.embed_query(root, query.q)

    # Load all stored embeddings (feasible for repo-scale corpora)
    rows = conn.execute(
        "SELECT resource_id, resource_type, vector_blob FROM embeddings"
    ).fetchall()

    scored: list[tuple[float, str, str]] = []
    for row in rows:
        vec = np.frombuffer(row[2], dtype=np.float32).copy()
        sim = _cosine_similarity(query_vec, vec)
        scored.append((sim, row[0], row[1]))

    # Apply author / type / date filters via a join to entries / events
    if query.type or query.author or query.date_from or query.date_to or query.tag:
        scored = _apply_filters(conn, scored, query)

    scored.sort(key=lambda item: (-item[0], item[2], item[1]))
    scored = scored[: query.limit]

    hits: list[SearchHit] = []
    for rank, (sim, resource_id, resource_type) in enumerate(scored, start=1):
        hits.append(
            SearchHit(
                resource_id=resource_id,
                resource_type=resource_type,
                score=sim,
                match_modes=["semantic"],
                explanation=SearchHitExplanation(
                    semantic_rank=rank,
                ),
            )
        )
    return hits


def search_hybrid(
    root: Path,
    conn: sqlite3.Connection,
    query: SearchQuery,
) -> list[SearchHit]:
    """Merge lexical and semantic candidates with RRF and return ranked hits."""
    # Collect lexical hits (up to limit * 2 to get broad candidates)
    broad_query = query.model_copy(update={"limit": query.limit * 2, "lexical_only": True})
    lexical_hits = _fts.search_lexical(conn, broad_query)

    # Collect semantic hits
    broad_sem_query = query.model_copy(update={"limit": query.limit * 2})
    semantic_hits = search_semantic(root, conn, broad_sem_query)

    # Build rank maps: resource_id -> rank (1-based)
    lex_rank: dict[str, int] = {h.resource_id: i + 1 for i, h in enumerate(lexical_hits)}
    sem_rank: dict[str, int] = {h.resource_id: i + 1 for i, h in enumerate(semantic_hits)}

    # Union of candidate IDs
    all_ids: set[str] = set(lex_rank) | set(sem_rank)

    # Compute RRF scores
    merged: list[tuple[float, str]] = []
    for rid in all_ids:
        score = 0.0
        if rid in lex_rank:
            score += _rrf_score(lex_rank[rid])
        if rid in sem_rank:
            score += _rrf_score(sem_rank[rid])
        merged.append((score, rid))

    merged.sort(key=lambda item: (-item[0], item[1]))
    merged = merged[: query.limit]

    # Build resource_type lookup
    resource_type_map: dict[str, str] = {}
    lexical_hit_map: dict[str, SearchHit] = {}
    for h in lexical_hits:
        resource_type_map[h.resource_id] = h.resource_type
        lexical_hit_map[h.resource_id] = h
    for h in semantic_hits:
        resource_type_map[h.resource_id] = h.resource_type

    hits: list[SearchHit] = []
    for rrf, rid in merged:
        lr = lex_rank.get(rid)
        sr = sem_rank.get(rid)
        modes: list[str] = []
        if lr is not None:
            modes.append("lexical")
        if sr is not None:
            modes.append("semantic")
        hits.append(
            SearchHit(
                resource_id=rid,
                resource_type=resource_type_map.get(rid, "entry"),
                score=rrf,
                match_modes=modes,
                explanation=SearchHitExplanation(
                    lexical_rank=lr,
                    semantic_rank=sr,
                    rrf_score=rrf,
                    matched_fields=(
                        lexical_hit_map[rid].explanation.matched_fields
                        if rid in lexical_hit_map
                        else []
                    ),
                ),
            )
        )
    return hits


def _apply_filters(
    conn: sqlite3.Connection,
    scored: list[tuple[float, str, str]],
    query: SearchQuery,
) -> list[tuple[float, str, str]]:
    """Remove candidates that do not pass entry/event-level filters."""
    kept: list[tuple[float, str, str]] = []
    for sim, resource_id, resource_type in scored:
        if resource_type == "entry" and _entry_passes_filter(conn, resource_id, query):
            kept.append((sim, resource_id, resource_type))
        elif resource_type == "event" and _event_passes_filter(conn, resource_id, query):
            kept.append((sim, resource_id, resource_type))
    return kept


def _entry_passes_filter(conn: sqlite3.Connection, public_id: str, query: SearchQuery) -> bool:
    clauses: list[str] = ["e.public_id = ?"]
    params: list[Any] = [public_id]
    if query.type:
        clauses.append("e.type = ?")
        params.append(query.type)
    if query.author:
        clauses.append("e.author = ?")
        params.append(query.author)
    if query.date_from:
        clauses.append("e.created_at >= ?")
        params.append(query.date_from)
    if query.date_to:
        clauses.append("e.created_at <= ?")
        params.append(query.date_to)
    if query.tag:
        clauses.append(
            "EXISTS (SELECT 1 FROM entry_tags t "
            "JOIN entries e2 ON t.entry_internal_id = e2.internal_id "
            "WHERE e2.public_id = e.public_id AND t.tag = ?)"
        )
        params.append(query.tag)
    sql = "SELECT 1 FROM entries e WHERE " + " AND ".join(clauses)
    return conn.execute(sql, params).fetchone() is not None


def _event_passes_filter(conn: sqlite3.Connection, public_id: str, query: SearchQuery) -> bool:
    # Events don't have type/author filters
    if query.type or query.author:
        return False
    clauses: list[str] = ["e.public_id = ?"]
    params: list[Any] = [public_id]
    if query.date_from:
        clauses.append("e.occurred_at >= ?")
        params.append(query.date_from)
    if query.date_to:
        clauses.append("e.occurred_at <= ?")
        params.append(query.date_to)
    if query.tag:
        clauses.append(
            "EXISTS (SELECT 1 FROM event_tags t "
            "JOIN events e2 ON t.event_internal_id = e2.internal_id "
            "WHERE e2.public_id = e.public_id AND t.tag = ?)"
        )
        params.append(query.tag)
    sql = "SELECT 1 FROM events e WHERE " + " AND ".join(clauses)
    return conn.execute(sql, params).fetchone() is not None
