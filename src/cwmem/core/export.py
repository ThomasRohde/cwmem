from __future__ import annotations

from typing import Any

import orjson

from cwmem.core.models import EntryRecord, EventRecord


def _json_inline(value: Any) -> str:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")


def _escape_quotes(value: str) -> str:
    return value.replace('"', '\\"')


def render_entry_markdown(entry: EntryRecord) -> str:
    front_matter = [
        "---",
        f'public_id: "{entry.public_id}"',
        f'internal_id: "{entry.internal_id}"',
        f'title: "{_escape_quotes(entry.title)}"',
        f'type: "{entry.type}"',
        f'status: "{entry.status}"',
        f'author: "{_escape_quotes(entry.author or "")}"',
        f'fingerprint: "{entry.fingerprint}"',
        f'created_at: "{entry.created_at}"',
        f'updated_at: "{entry.updated_at}"',
        f"tags: {_json_inline(entry.tags)}",
        f"related_ids: {_json_inline(entry.related_ids)}",
        f"entity_refs: {_json_inline(entry.entity_refs)}",
        f"provenance: {_json_inline(entry.provenance)}",
        f"metadata: {_json_inline(entry.metadata)}",
        "---",
        "",
        entry.body,
        "",
    ]
    return "\n".join(front_matter)


def render_entry_jsonl(entry: EntryRecord) -> str:
    payload = entry.model_dump(mode="json")
    return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode("utf-8") + "\n"


def render_event_jsonl(event: EventRecord) -> str:
    payload = event.model_dump(mode="json")
    return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode("utf-8") + "\n"
