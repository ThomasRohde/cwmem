from __future__ import annotations

from pathlib import Path

from cwmem.core.graph import graph_show, related
from cwmem.core.locking import read_lock_info
from cwmem.core.models import ListEntriesQuery, LogQuery, RelatedQuery, SearchHit, SearchQuery
from cwmem.core.repository import build_status_result
from cwmem.core.store import get_resource, get_stats, list_entries, list_events, search_entries
from cwmem.ui.view_models import DashboardSnapshot, ResourceRecord


class MemoryUIService:
    def __init__(self, root: Path) -> None:
        self.root = root

    def dashboard(self) -> DashboardSnapshot:
        status = build_status_result(self.root)
        stats = get_stats(self.root) if status.database_exists else None
        lock_info = read_lock_info(self.root)
        model_manifest = self.root / "models" / "model2vec" / "manifest.json"
        return DashboardSnapshot(
            status=status,
            stats=stats,
            lock_info=lock_info,
            model_manifest_present=model_manifest.is_file(),
        )

    def list_entries(
        self,
        *,
        tags: list[str] | None = None,
        entry_type: str | None = None,
        status: str | None = None,
        author: str | None = None,
        limit: int = 50,
    ):
        query = ListEntriesQuery.model_validate(
            {
                "tags": tags or [],
                "type": entry_type or None,
                "status": status or None,
                "author": author or None,
                "limit": limit,
            }
        )
        return list_entries(self.root, query)

    def search(
        self,
        *,
        q: str,
        tag: str | None = None,
        search_type: str | None = None,
        author: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        lexical_only: bool = False,
        semantic_only: bool = False,
        expand_graph: bool = False,
        limit: int = 20,
    ) -> list[tuple[SearchHit, ResourceRecord]]:
        query = SearchQuery.model_validate(
            {
                "q": q,
                "tag": tag or None,
                "type": search_type or None,
                "author": author or None,
                "date_from": date_from or None,
                "date_to": date_to or None,
                "lexical_only": lexical_only,
                "semantic_only": semantic_only,
                "expand_graph": expand_graph,
                "limit": limit,
            }
        )
        try:
            hits = search_entries(self.root, query)
        except FileNotFoundError as exc:
            if semantic_only or not lexical_only:
                raise RuntimeError(
                    "Semantic search is unavailable. Run `cwmem build` or switch to lexical."
                ) from exc
            raise
        return [(hit, get_resource(self.root, hit.resource_id)) for hit in hits]

    def preview_resource(self, resource_id: str) -> ResourceRecord:
        return get_resource(self.root, resource_id)

    def log(
        self,
        *,
        resource: str | None = None,
        event_type: str | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
    ):
        query = LogQuery.model_validate(
            {
                "resource": resource or None,
                "event_type": event_type or None,
                "tags": tags or [],
                "limit": limit,
            }
        )
        return list_events(self.root, query)

    def related(
        self,
        *,
        resource_id: str,
        relation_type: str | None = None,
        depth: int = 1,
        limit: int = 50,
    ):
        query = RelatedQuery.model_validate(
            {
                "resource_id": resource_id,
                "relation_type": relation_type or None,
                "depth": depth,
                "limit": limit,
                "include_provenance": True,
            }
        )
        return related(self.root, query)

    def graph(
        self,
        *,
        resource_id: str,
        relation_type: str | None = None,
        depth: int = 1,
        limit: int = 50,
    ):
        query = RelatedQuery.model_validate(
            {
                "resource_id": resource_id,
                "relation_type": relation_type or None,
                "depth": depth,
                "limit": limit,
                "include_provenance": True,
            }
        )
        return graph_show(self.root, query)
