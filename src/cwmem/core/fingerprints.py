from __future__ import annotations

import hashlib
from typing import Any

import orjson

from cwmem.core.models import EdgeRecord, EntityRecord, EntryRecord, EventRecord


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _digest(payload: dict[str, Any]) -> str:
    canonical = orjson.dumps(_normalize(payload), option=orjson.OPT_SORT_KEYS)
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def compute_entry_fingerprint(entry: EntryRecord | dict[str, Any]) -> str:
    data = entry.model_dump(mode="json") if isinstance(entry, EntryRecord) else dict(entry)
    return _digest(
        {
            "title": data["title"],
            "body": data["body"],
            "type": data["type"],
            "status": data["status"],
            "author": data.get("author"),
            "tags": sorted(set(data.get("tags", []))),
            "provenance": data.get("provenance", {}),
            "related_ids": sorted(set(data.get("related_ids", []))),
            "entity_refs": sorted(set(data.get("entity_refs", []))),
            "metadata": data.get("metadata", {}),
        }
    )


def compute_event_fingerprint(event: EventRecord | dict[str, Any]) -> str:
    data = event.model_dump(mode="json") if isinstance(event, EventRecord) else dict(event)
    normalized_resources = sorted(
        (
            {"resource_id": item["resource_id"], "role": item.get("role", "subject")}
            for item in data.get("resources", [])
        ),
        key=lambda item: (item["resource_id"], item["role"]),
    )
    return _digest(
        {
            "event_type": data["event_type"],
            "body": data["body"],
            "author": data.get("author"),
            "tags": sorted(set(data.get("tags", []))),
            "resources": normalized_resources,
            "related_ids": sorted(set(data.get("related_ids", []))),
            "entity_refs": sorted(set(data.get("entity_refs", []))),
            "metadata": data.get("metadata", {}),
            "occurred_at": data["occurred_at"],
        }
    )


def compute_entity_fingerprint(entity: EntityRecord | dict[str, Any]) -> str:
    data = entity.model_dump(mode="json") if isinstance(entity, EntityRecord) else dict(entity)
    return _digest(
        {
            "entity_type": data["entity_type"],
            "name": data["name"],
            "description": data["description"],
            "status": data["status"],
            "aliases": sorted(set(data.get("aliases", []))),
            "tags": sorted(set(data.get("tags", []))),
            "provenance": data.get("provenance", {}),
            "metadata": data.get("metadata", {}),
        }
    )


def compute_edge_fingerprint(edge: EdgeRecord | dict[str, Any]) -> str:
    data = edge.model_dump(mode="json") if isinstance(edge, EdgeRecord) else dict(edge)
    return _digest(
        {
            "source_id": data["source_id"],
            "source_type": data["source_type"],
            "target_id": data["target_id"],
            "target_type": data["target_type"],
            "relation_type": data["relation_type"],
            "provenance": data["provenance"],
            "confidence": round(float(data["confidence"]), 6),
            "is_inferred": bool(data.get("is_inferred", False)),
            "created_by": data["created_by"],
            "metadata": data.get("metadata", {}),
        }
    )
