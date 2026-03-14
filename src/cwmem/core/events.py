from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from cwmem.core.fingerprints import compute_event_fingerprint
from cwmem.core.ids import generate_internal_id, next_public_id
from cwmem.core.models import CreateEventInput, EntryRecord, EventRecord, EventResource


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _normalize_tags(tags: list[str]) -> list[str]:
    return sorted({tag.strip() for tag in tags if tag.strip()})


def _normalize_resources(resources: list[EventResource]) -> list[EventResource]:
    unique: dict[tuple[str, str], EventResource] = {}
    for resource in resources:
        identifier = resource.resource_id.strip()
        role = resource.role.strip() or "subject"
        if identifier:
            unique[(identifier, role)] = EventResource(resource_id=identifier, role=role)
    return sorted(unique.values(), key=lambda item: (item.resource_id, item.role))


def append_event(conn: sqlite3.Connection, event_input: CreateEventInput) -> EventRecord:
    created_at = _utc_now()
    occurred_at = event_input.occurred_at or created_at
    tags = _normalize_tags(event_input.tags)
    resources = _normalize_resources(event_input.resources)
    record = EventRecord(
        internal_id=generate_internal_id(),
        public_id=next_public_id(conn, "evt"),
        event_type=event_input.event_type,
        body=event_input.body,
        author=event_input.author,
        tags=tags,
        resources=resources,
        related_ids=sorted(set(event_input.related_ids)),
        entity_refs=sorted(set(event_input.entity_refs)),
        metadata=dict(event_input.metadata),
        fingerprint="",
        occurred_at=occurred_at,
        created_at=created_at,
    )
    record.fingerprint = compute_event_fingerprint(record)

    conn.execute(
        """
        INSERT INTO events(
            internal_id,
            public_id,
            event_type,
            body,
            author,
            occurred_at,
            created_at,
            related_ids_json,
            entity_refs_json,
            metadata_json,
            fingerprint
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.internal_id,
            record.public_id,
            record.event_type,
            record.body,
            record.author,
            record.occurred_at,
            record.created_at,
            _json_dump(record.related_ids),
            _json_dump(record.entity_refs),
            _json_dump(record.metadata),
            record.fingerprint,
        ),
    )
    conn.executemany(
        "INSERT OR IGNORE INTO event_tags(event_internal_id, tag, created_at) VALUES (?, ?, ?)",
        [(record.internal_id, tag, created_at) for tag in record.tags],
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO event_resources(event_internal_id, resource_public_id, role)
        VALUES (?, ?, ?)
        """,
        [
            (record.internal_id, resource.resource_id, resource.role)
            for resource in record.resources
        ],
    )
    return record


def build_entry_lifecycle_event(
    entry: EntryRecord,
    *,
    event_type: str,
    previous_fingerprint: str | None = None,
    changed_fields: list[str] | None = None,
) -> CreateEventInput:
    metadata: dict[str, Any] = {
        "entry_public_id": entry.public_id,
        "entry_fingerprint": entry.fingerprint,
    }
    if previous_fingerprint is not None:
        metadata["previous_fingerprint"] = previous_fingerprint
    if changed_fields:
        metadata["changed_fields"] = changed_fields

    action = "created" if event_type.endswith(".created") else "updated"
    return CreateEventInput(
        event_type=event_type,
        body=f"Entry {entry.public_id} {action}: {entry.title}",
        author=entry.author,
        tags=entry.tags,
        resources=[EventResource(resource_id=entry.public_id, role="subject")],
        related_ids=entry.related_ids,
        entity_refs=entry.entity_refs,
        metadata=metadata,
        occurred_at=entry.updated_at if action == "updated" else entry.created_at,
    )


def _json_dump(value: Any) -> str:
    import orjson

    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")
