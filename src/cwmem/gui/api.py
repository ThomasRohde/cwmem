from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from cwmem.core.models import (
    CreateEdgeInput,
    CreateEntryInput,
    GraphNeighborhood,
    GraphNode,
    TagMutationInput,
)
from cwmem.ui.actions import add_entry_action, link_resources_action, mutate_tags_action
from cwmem.ui.services import MemoryUIService
from cwmem.ui.view_models import resource_kind, resource_label, resource_summary


def _serialize(obj: object) -> Any:
    """Convert Pydantic models and dataclasses to JSON-safe dicts."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")  # type: ignore[union-attr]
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses

        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            result: dict[str, Any] = {}
            for f in dataclasses.fields(obj):
                val = getattr(obj, f.name)
                result[f.name] = _serialize(val)
            return result
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, tuple):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


class AddEntryBody(BaseModel):
    title: str
    body: str
    type: str = "note"
    status: str = "active"
    author: str | None = None
    tags: list[str] = []
    provenance: dict[str, Any] = {}
    related_ids: list[str] = []
    entity_refs: list[str] = []
    metadata: dict[str, Any] = {}


class MutateTagsBody(BaseModel):
    resource_id: str
    tags: list[str]


class LinkBody(BaseModel):
    source_id: str
    target_id: str
    relation_type: str
    provenance: str = "explicit_user"
    confidence: float = 1.0
    metadata: dict[str, Any] = {}


def build_router(root: Path) -> APIRouter:
    router = APIRouter(prefix="/api")
    service = MemoryUIService(root)

    @router.get("/dashboard")
    async def dashboard() -> Any:
        snap = await asyncio.to_thread(service.dashboard)
        return _serialize(snap)

    @router.get("/entries")
    async def entries(
        tag: list[str] | None = Query(None),  # noqa: B008
        type: str | None = None,
        status: str | None = None,
        author: str | None = None,
        limit: int = 50,
    ) -> Any:
        items = await asyncio.to_thread(
            service.list_entries,
            tags=tag,
            entry_type=type,
            status=status,
            author=author,
            limit=limit,
        )
        return [_serialize(item) for item in items]

    @router.get("/search")
    async def search_entries(
        q: str = "",
        tag: str | None = None,
        type: str | None = None,
        author: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        mode: str | None = None,
        expand: bool = False,
        limit: int = 20,
    ) -> Any:
        if not q.strip():
            return []
        lexical_only = mode == "lexical"
        semantic_only = mode == "semantic"
        try:
            results = await asyncio.to_thread(
                service.search,
                q=q,
                tag=tag,
                search_type=type,
                author=author,
                date_from=date_from,
                date_to=date_to,
                lexical_only=lexical_only,
                semantic_only=semantic_only,
                expand_graph=expand,
                limit=limit,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return [
            {
                "hit": _serialize(hit),
                "resource": _serialize(resource),
                "kind": resource_kind(resource),
                "label": resource_label(resource),
                "summary": resource_summary(resource),
            }
            for hit, resource in results
        ]

    @router.get("/resources/{resource_id:path}")
    async def get_resource(resource_id: str) -> Any:
        try:
            resource = await asyncio.to_thread(service.preview_resource, resource_id)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "resource": _serialize(resource),
            "kind": resource_kind(resource),
            "label": resource_label(resource),
            "summary": resource_summary(resource),
        }

    @router.get("/events")
    async def events(
        resource: str | None = None,
        event_type: str | None = None,
        tag: list[str] | None = Query(None),  # noqa: B008
        limit: int = 50,
    ) -> Any:
        items = await asyncio.to_thread(
            service.log,
            resource=resource,
            event_type=event_type,
            tags=tag,
            limit=limit,
        )
        return [_serialize(item) for item in items]

    @router.get("/related/{resource_id:path}")
    async def related(
        resource_id: str,
        relation_type: str | None = None,
        depth: int = 1,
        limit: int = 50,
    ) -> Any:
        items = await asyncio.to_thread(
            service.related,
            resource_id=resource_id,
            relation_type=relation_type,
            depth=depth,
            limit=limit,
        )
        return [_serialize(item) for item in items]

    @router.get("/graph-overview")
    async def graph_overview(limit: int = 200) -> Any:
        neighborhood = await asyncio.to_thread(
            _build_graph_overview, root, limit
        )
        return _serialize(neighborhood)

    @router.get("/graph/{resource_id:path}")
    async def graph(
        resource_id: str,
        relation_type: str | None = None,
        depth: int = 1,
        limit: int = 50,
    ) -> Any:
        neighborhood = await asyncio.to_thread(
            service.graph,
            resource_id=resource_id,
            relation_type=relation_type,
            depth=depth,
            limit=limit,
        )
        return _serialize(neighborhood)

    @router.post("/entries")
    async def create_entry(body: AddEntryBody, dry_run: bool = False) -> Any:
        entry_input = CreateEntryInput.model_validate(body.model_dump())
        result = await asyncio.to_thread(
            add_entry_action, root, entry_input, dry_run=dry_run
        )
        return _serialize(result)

    @router.post("/tags")
    async def mutate_tags(
        body: MutateTagsBody, add: bool = True, dry_run: bool = False
    ) -> Any:
        mutation_input = TagMutationInput.model_validate(body.model_dump())
        result = await asyncio.to_thread(
            mutate_tags_action, root, mutation_input, add=add, dry_run=dry_run
        )
        return _serialize(result)

    @router.post("/edges")
    async def create_edge(body: LinkBody, dry_run: bool = False) -> Any:
        edge_input = CreateEdgeInput.model_validate(body.model_dump())
        result = await asyncio.to_thread(
            link_resources_action, root, edge_input, dry_run=dry_run
        )
        return _serialize(result)

    return router


def _build_graph_overview(root: Path, limit: int) -> GraphNeighborhood:
    """Return all entries, entities, and edges as a single graph."""
    from cwmem.core.store import _connect

    conn = _connect(root)
    try:
        nodes: list[GraphNode] = []
        # Entries
        rows = conn.execute(
            "SELECT public_id, title FROM entries ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        for row in rows:
            nodes.append(
                GraphNode(resource_id=row["public_id"], resource_type="entry", label=row["title"])
            )
        # Entities
        rows = conn.execute(
            "SELECT public_id, name FROM entities ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        for row in rows:
            nodes.append(
                GraphNode(
                    resource_id=row["public_id"], resource_type="entity", label=row["name"]
                )
            )
        # Events (only those referenced by edges)
        rows = conn.execute(
            "SELECT DISTINCT e.public_id, e.event_type, e.body FROM events e "
            "INNER JOIN edges ed ON e.public_id = ed.source_id OR e.public_id = ed.target_id "
            "ORDER BY e.occurred_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        node_ids = {n.resource_id for n in nodes}
        for row in rows:
            if row["public_id"] not in node_ids:
                label = row["body"].strip().split("\n")[0][:120] if row["body"].strip() else row[
                    "event_type"
                ]
                nodes.append(
                    GraphNode(resource_id=row["public_id"], resource_type="event", label=label)
                )
                node_ids.add(row["public_id"])

        # All edges
        from cwmem.core.graph import _edge_from_row

        edge_rows = conn.execute(
            "SELECT * FROM edges ORDER BY is_inferred ASC, confidence DESC LIMIT ?",
            (limit * 4,),
        ).fetchall()
        edges = [_edge_from_row(r) for r in edge_rows]

        # Build a synthetic root from the first entry (or first node)
        root_node = nodes[0] if nodes else GraphNode(
            resource_id="empty", resource_type="entry", label="(empty graph)"
        )
        return GraphNeighborhood(root=root_node, depth=0, nodes=nodes[1:], edges=edges)
    finally:
        conn.close()
