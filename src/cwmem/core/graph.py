from __future__ import annotations

import hashlib
import sqlite3
from collections import deque
from pathlib import Path
from typing import Any

from cwmem.core import fts as _fts
from cwmem.core import store as _store
from cwmem.core.fingerprints import compute_edge_fingerprint, compute_entity_fingerprint
from cwmem.core.ids import generate_internal_id, next_public_id
from cwmem.core.models import (
    CreateEdgeInput,
    CreateEntityInput,
    EdgeRecord,
    EntityRecord,
    GraphNeighborhood,
    GraphNode,
    RelatedHit,
    RelatedQuery,
    SearchHit,
    SearchHitExplanation,
)


def add_entity(root: Path, entity_input: CreateEntityInput) -> EntityRecord:
    conn = _store._connect(root)
    try:
        with conn:
            now = _store._utc_now()
            aliases = _normalize_aliases(entity_input.aliases)
            tags = _store._normalize_tags(entity_input.tags)
            entity_type = entity_input.entity_type.strip()
            name = entity_input.name.strip()
            if not entity_type:
                _store._raise_validation(
                    "Entity type cannot be empty.",
                    details={"entity_type": entity_input.entity_type},
                    suggested_action="Provide `--entity-type` with a non-empty value.",
                )
            if not name:
                _store._raise_validation(
                    "Entity name cannot be empty.",
                    details={"name": entity_input.name},
                    suggested_action="Provide `--name` with a non-empty value.",
                )

            record = EntityRecord(
                internal_id=generate_internal_id(),
                public_id=next_public_id(conn, "ent"),
                entity_type=entity_type,
                name=name,
                description=entity_input.description.strip(),
                status=entity_input.status.strip() or "active",
                aliases=aliases,
                tags=tags,
                provenance=dict(entity_input.provenance),
                metadata=dict(entity_input.metadata),
                fingerprint="",
                created_at=now,
                updated_at=now,
            )
            record.fingerprint = compute_entity_fingerprint(record)
            entity_columns = _store._table_columns(conn, "entities")
            if "kind" in entity_columns:
                conn.execute(
                    """
                    INSERT INTO entities(
                        internal_id,
                        public_id,
                        kind,
                        entity_type,
                        name,
                        description,
                        status,
                        aliases_json,
                        provenance_json,
                        metadata_json,
                        fingerprint,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.internal_id,
                        record.public_id,
                        record.entity_type,
                        record.entity_type,
                        record.name,
                        record.description,
                        record.status,
                        _store._json_dump(record.aliases),
                        _store._json_dump(record.provenance),
                        _store._json_dump(record.metadata),
                        record.fingerprint,
                        record.created_at,
                        record.updated_at,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO entities(
                        internal_id,
                        public_id,
                        entity_type,
                        name,
                        description,
                        status,
                        aliases_json,
                        provenance_json,
                        metadata_json,
                        fingerprint,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.internal_id,
                        record.public_id,
                        record.entity_type,
                        record.name,
                        record.description,
                        record.status,
                        _store._json_dump(record.aliases),
                        _store._json_dump(record.provenance),
                        _store._json_dump(record.metadata),
                        record.fingerprint,
                        record.created_at,
                        record.updated_at,
                    ),
                )
            conn.executemany(
                """
                INSERT OR IGNORE INTO entity_tags(entity_internal_id, tag, created_at)
                VALUES (?, ?, ?)
                """,
                [(record.internal_id, tag, now) for tag in record.tags],
            )
            _fts.upsert_entity_fts(conn, record)
            return record
    finally:
        conn.close()


def add_edge(root: Path, edge_input: CreateEdgeInput) -> EdgeRecord:
    conn = _store._connect(root)
    try:
        with conn:
            source_id = edge_input.source_id.strip()
            target_id = edge_input.target_id.strip()
            relation_type = edge_input.relation_type.strip()
            provenance = edge_input.provenance.strip() or "explicit_user"
            if not source_id or not target_id:
                _store._raise_validation(
                    "Both source and target resource IDs are required.",
                    details={
                        "source_id": edge_input.source_id,
                        "target_id": edge_input.target_id,
                    },
                    suggested_action="Provide both resource IDs when calling `cwmem link`.",
                )
            if not relation_type:
                _store._raise_validation(
                    "Relation type cannot be empty.",
                    details={"relation_type": edge_input.relation_type},
                    suggested_action="Provide `--relation` with a non-empty value.",
                )
            if source_id == target_id:
                _store._raise_validation(
                    "Self-links are not supported.",
                    details={"resource_id": source_id},
                    suggested_action="Link two distinct resources instead.",
                )

            _store._validate_resources_exist(conn, [source_id, target_id])
            existing = conn.execute(
                """
                SELECT public_id
                FROM edges
                WHERE source_id = ?
                  AND target_id = ?
                  AND relation_type = ?
                  AND is_inferred = 0
                """,
                (source_id, target_id, relation_type),
            ).fetchone()
            if existing is not None:
                _store._raise_validation(
                    "An explicit edge with the same source, target, and relation already exists.",
                    details={
                        "source_id": source_id,
                        "target_id": target_id,
                        "relation_type": relation_type,
                        "edge_id": existing["public_id"],
                    },
                    suggested_action=(
                        "Reuse the existing edge or choose a different relation or target."
                    ),
                )

            now = _store._utc_now()
            record = EdgeRecord(
                internal_id=generate_internal_id(),
                public_id=next_public_id(conn, "edg"),
                source_id=source_id,
                source_type=_store._resource_kind(source_id),
                target_id=target_id,
                target_type=_store._resource_kind(target_id),
                relation_type=relation_type,
                provenance=provenance,
                confidence=edge_input.confidence,
                is_inferred=False,
                created_by="user",
                metadata=dict(edge_input.metadata),
                fingerprint="",
                created_at=now,
                updated_at=now,
            )
            record.fingerprint = compute_edge_fingerprint(record)
            _insert_edge(conn, record)
            return record
    finally:
        conn.close()


def rebuild_inferred_edges(conn: sqlite3.Connection) -> int:
    conn.execute("DELETE FROM edges WHERE is_inferred = 1")

    entry_rows = conn.execute(
        "SELECT public_id, entity_refs_json FROM entries ORDER BY public_id ASC"
    ).fetchall()
    refs_to_entries: dict[str, list[str]] = {}
    for row in entry_rows:
        refs = sorted(
            {
                ref
                for ref in _store._json_load(row["entity_refs_json"])
                if isinstance(ref, str) and ref.startswith("ent-")
            }
        )
        for ref in refs:
            refs_to_entries.setdefault(ref, []).append(row["public_id"])

    explicit_pairs = {
        frozenset((row["source_id"], row["target_id"]))
        for row in conn.execute(
            "SELECT source_id, target_id FROM edges WHERE is_inferred = 0"
        ).fetchall()
    }

    pair_to_refs: dict[tuple[str, str], set[str]] = {}
    for ref, entry_ids in refs_to_entries.items():
        unique_ids = sorted(set(entry_ids))
        for left_index, left_id in enumerate(unique_ids):
            for right_id in unique_ids[left_index + 1 :]:
                pair = (left_id, right_id)
                if frozenset(pair) in explicit_pairs:
                    continue
                pair_to_refs.setdefault(pair, set()).add(ref)

    written = 0
    now = _store._utc_now()
    for pair, shared_refs in sorted(pair_to_refs.items()):
        record = EdgeRecord(
            internal_id=generate_internal_id(),
            public_id=_inferred_public_id(pair[0], pair[1], shared_refs),
            source_id=pair[0],
            source_type="entry",
            target_id=pair[1],
            target_type="entry",
            relation_type="related_to",
            provenance="inferred_rule",
            confidence=0.35,
            is_inferred=True,
            created_by="build",
            metadata={
                "rule": "shared_entity_ref",
                "shared_entity_refs": sorted(shared_refs),
            },
            fingerprint="",
            created_at=now,
            updated_at=now,
        )
        record.fingerprint = compute_edge_fingerprint(record)
        _insert_edge(conn, record)
        written += 1

    return written


def related(root: Path, query: RelatedQuery) -> list[RelatedHit]:
    conn = _store._connect(root)
    try:
        _store._validate_resources_exist(conn, [query.resource_id])
        hits, _ = _traverse(
            conn,
            query.resource_id,
            depth=query.depth,
            limit=query.limit,
            relation_type=query.relation_type,
        )
        return hits
    finally:
        conn.close()


def graph_show(root: Path, query: RelatedQuery) -> GraphNeighborhood:
    conn = _store._connect(root)
    try:
        _store._validate_resources_exist(conn, [query.resource_id])
        hits, traversed_edges = _traverse(
            conn,
            query.resource_id,
            depth=query.depth,
            limit=query.limit,
            relation_type=query.relation_type,
        )
        nodes = [hit.resource for hit in hits]
        edges = [traversed_edges[key] for key in sorted(traversed_edges)]
        return GraphNeighborhood(
            root=_node_from_resource(conn, query.resource_id),
            depth=query.depth,
            nodes=nodes,
            edges=edges,
        )
    finally:
        conn.close()


def expand_search_hits(
    conn: sqlite3.Connection, hits: list[SearchHit], limit: int
) -> list[SearchHit]:
    if not hits:
        return []

    expanded = list(hits)
    seen = {hit.resource_id for hit in hits}
    for hit in hits:
        if len(expanded) >= limit:
            break
        for edge in _edges_for_resource(conn, hit.resource_id):
            neighbor_id, neighbor_type = _neighbor(edge, hit.resource_id)
            if neighbor_id in seen:
                continue
            seen.add(neighbor_id)
            expanded.append(
                SearchHit(
                    resource_id=neighbor_id,
                    resource_type=neighbor_type,
                    score=max(hit.score * 0.5, 0.000001),
                    match_modes=["graph_expansion"],
                    explanation=SearchHitExplanation(
                        expanded_from=hit.resource_id,
                        via_edge={
                            "edge_id": edge.public_id,
                            "relation_type": edge.relation_type,
                            "provenance": edge.provenance,
                            "confidence": edge.confidence,
                            "is_inferred": edge.is_inferred,
                        },
                    ),
                )
            )
            if len(expanded) >= limit:
                break
    return expanded[:limit]


def _traverse(
    conn: sqlite3.Connection,
    root_id: str,
    *,
    depth: int,
    limit: int,
    relation_type: str | None,
) -> tuple[list[RelatedHit], dict[str, EdgeRecord]]:
    seen = {root_id}
    queue: deque[tuple[str, int, list[EdgeRecord]]] = deque([(root_id, 0, [])])
    hits: list[RelatedHit] = []
    traversed_edges: dict[str, EdgeRecord] = {}

    while queue and len(hits) < limit:
        current_id, current_depth, path = queue.popleft()
        if current_depth >= depth:
            continue
        for edge in _edges_for_resource(conn, current_id, relation_type=relation_type):
            traversed_edges[edge.public_id] = edge
            neighbor_id, neighbor_type = _neighbor(edge, current_id)
            if neighbor_id in seen:
                continue
            seen.add(neighbor_id)
            next_path = [*path, edge]
            node = _node_from_resource(conn, neighbor_id, neighbor_type)
            hits.append(
                RelatedHit(
                    resource_id=neighbor_id,
                    resource_type=neighbor_type,
                    depth=current_depth + 1,
                    resource=node,
                    path=next_path,
                )
            )
            queue.append((neighbor_id, current_depth + 1, next_path))
            if len(hits) >= limit:
                break

    return hits, traversed_edges


def _edges_for_resource(
    conn: sqlite3.Connection,
    resource_id: str,
    *,
    relation_type: str | None = None,
) -> list[EdgeRecord]:
    sql = [
        "SELECT * FROM edges",
        "WHERE (source_id = ? OR target_id = ?)",
    ]
    params: list[Any] = [resource_id, resource_id]
    if relation_type:
        sql.append("AND relation_type = ?")
        params.append(relation_type)
    sql.append(
        "ORDER BY is_inferred ASC, confidence DESC, relation_type ASC, public_id ASC"
    )
    rows = conn.execute(" ".join(sql), params).fetchall()
    return [_edge_from_row(row) for row in rows]


def _node_from_resource(
    conn: sqlite3.Connection, resource_id: str, resource_type: str | None = None
) -> GraphNode:
    kind = resource_type or _store._resource_kind(resource_id)
    if kind == "entry":
        entry = _store._get_entry_by_public_id(conn, resource_id)
        return GraphNode(resource_id=entry.public_id, resource_type="entry", label=entry.title)
    if kind == "event":
        event = _store._get_event_by_public_id(conn, resource_id)
        label = event.body.strip().splitlines()[0] if event.body.strip() else event.event_type
        return GraphNode(resource_id=event.public_id, resource_type="event", label=label[:120])
    row = conn.execute("SELECT * FROM entities WHERE public_id = ?", (resource_id,)).fetchone()
    if row is None:
        _store._raise_validation(
            "Entity not found.",
            details={"resource_id": resource_id},
            suggested_action="Create the entity first or choose an existing entity ID.",
        )
    return GraphNode(resource_id=row["public_id"], resource_type="entity", label=row["name"])


def _edge_from_row(row: sqlite3.Row) -> EdgeRecord:
    return EdgeRecord(
        internal_id=row["internal_id"],
        public_id=row["public_id"],
        source_id=row["source_id"],
        source_type=row["source_type"],
        target_id=row["target_id"],
        target_type=row["target_type"],
        relation_type=row["relation_type"],
        provenance=row["provenance"],
        confidence=float(row["confidence"]),
        is_inferred=bool(row["is_inferred"]),
        created_by=row["created_by"],
        metadata=_store._json_load(row["metadata_json"]),
        fingerprint=row["fingerprint"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _insert_edge(conn: sqlite3.Connection, record: EdgeRecord) -> None:
    conn.execute(
        """
        INSERT INTO edges(
            internal_id,
            public_id,
            source_id,
            source_type,
            target_id,
            target_type,
            relation_type,
            provenance,
            confidence,
            is_inferred,
            created_by,
            metadata_json,
            fingerprint,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.internal_id,
            record.public_id,
            record.source_id,
            record.source_type,
            record.target_id,
            record.target_type,
            record.relation_type,
            record.provenance,
            record.confidence,
            int(record.is_inferred),
            record.created_by,
            _store._json_dump(record.metadata),
            record.fingerprint,
            record.created_at,
            record.updated_at,
        ),
    )


def _normalize_aliases(aliases: list[str]) -> list[str]:
    return sorted({alias.strip() for alias in aliases if alias.strip()})


def _neighbor(edge: EdgeRecord, resource_id: str) -> tuple[str, str]:
    if edge.source_id == resource_id:
        return edge.target_id, edge.target_type
    return edge.source_id, edge.source_type


def _inferred_public_id(source_id: str, target_id: str, shared_refs: set[str]) -> str:
    digest = hashlib.sha256(
        "|".join([source_id, target_id, *sorted(shared_refs)]).encode("utf-8")
    ).hexdigest()
    return f"iedg-{digest[:12]}"
