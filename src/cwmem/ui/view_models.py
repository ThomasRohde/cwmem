from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import orjson

from cwmem.core.models import (
    EdgeRecord,
    EntityRecord,
    EntryRecord,
    EventRecord,
    LockInfo,
    RelatedHit,
    SearchHit,
    StatsResult,
    StatusResult,
)

type ResourceRecord = EntryRecord | EventRecord | EntityRecord


@dataclass(slots=True)
class DashboardSnapshot:
    status: StatusResult
    stats: StatsResult | None
    lock_info: LockInfo | None
    model_manifest_present: bool


def entry_row(entry: EntryRecord) -> tuple[str, ...]:
    return (
        entry.public_id,
        entry.type,
        entry.status,
        _truncate(entry.title, 48),
        entry.author or "-",
        _short_timestamp(entry.updated_at),
    )


def search_row(hit: SearchHit, resource: ResourceRecord) -> tuple[str, ...]:
    return (
        hit.resource_id,
        resource_kind(resource),
        ",".join(hit.match_modes),
        f"{hit.score:.3f}",
        _truncate(resource_label(resource), 48),
        _truncate(resource_summary(resource), 56),
    )


def event_row(event: EventRecord) -> tuple[str, ...]:
    summary = event.metadata.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = resource_summary(event)
    return (
        event.public_id,
        event.event_type,
        _short_timestamp(event.occurred_at),
        _truncate(summary, 48),
        str(len(event.resources)),
    )


def related_row(hit: RelatedHit) -> tuple[str, ...]:
    return (
        hit.resource_id,
        hit.resource_type,
        str(hit.depth),
        _truncate(hit.resource.label, 42),
        " -> ".join(edge.relation_type for edge in hit.path) or "-",
    )


def edge_row(edge: EdgeRecord) -> tuple[str, ...]:
    return (
        edge.public_id,
        edge.relation_type,
        edge.source_id,
        edge.target_id,
        f"{edge.confidence:.2f}",
        edge.provenance,
    )


def dashboard_markdown(snapshot: DashboardSnapshot) -> str:
    status = snapshot.status
    lines = [
        "# Repository memory overview",
        "",
        f"- Initialized: {'yes' if status.initialized else 'no'}",
        f"- Database present: {'yes' if status.database_exists else 'no'}",
        f"- Model manifest present: {'yes' if snapshot.model_manifest_present else 'no'}",
        f"- Missing paths: {len(status.missing_paths)}",
        f"- Empty tracked surfaces: {len(status.empty_surfaces)}",
    ]
    if snapshot.stats is not None:
        stats = snapshot.stats
        lines.extend(
            [
                "",
                "## Runtime counts",
                "",
                f"- Entries: {stats.entries}",
                f"- Events: {stats.events}",
                f"- Entities: {stats.entities}",
                f"- Edges: {stats.edges}",
                f"- Embeddings: {stats.embeddings}",
                f"- Last build: {stats.last_build_at or 'n/a'}",
                f"- Embedding model: {stats.embedding_model or 'n/a'}",
            ]
        )
    if snapshot.lock_info is not None:
        lock = snapshot.lock_info
        lines.extend(
            [
                "",
                "## Active lock",
                "",
                f"- PID: {lock.pid}",
                f"- Host: {lock.hostname}",
                f"- Command: {lock.command}",
                f"- Request: {lock.request_id}",
                f"- Acquired: {lock.acquired_at}",
            ]
        )
    if status.missing_paths:
        lines.extend(
            [
                "",
                "## Missing paths",
                "",
                *[f"- `{path}`" for path in status.missing_paths],
            ]
        )
    return "\n".join(lines)


def resource_markdown(resource: ResourceRecord) -> str:
    if isinstance(resource, EntryRecord):
        lines = [
            f"# {resource.title}",
            "",
            f"- ID: `{resource.public_id}`",
            f"- Type: `{resource.type}`",
            f"- Status: `{resource.status}`",
            f"- Author: {resource.author or 'n/a'}",
            f"- Updated: {resource.updated_at}",
        ]
        if resource.tags:
            lines.append(f"- Tags: {', '.join(f'`{tag}`' for tag in resource.tags)}")
        if resource.entity_refs:
            lines.append(f"- Entity refs: {', '.join(f'`{ref}`' for ref in resource.entity_refs)}")
        if resource.related_ids:
            lines.append(f"- Related IDs: {', '.join(f'`{ref}`' for ref in resource.related_ids)}")
        lines.extend(["", "## Body", "", resource.body])
        return "\n".join(lines)

    if isinstance(resource, EventRecord):
        summary = resource.metadata.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            summary = resource.event_type
        lines = [
            f"# {summary}",
            "",
            f"- ID: `{resource.public_id}`",
            f"- Event type: `{resource.event_type}`",
            f"- Actor: {resource.author or 'n/a'}",
            f"- Occurred at: {resource.occurred_at}",
        ]
        if resource.tags:
            lines.append(f"- Tags: {', '.join(f'`{tag}`' for tag in resource.tags)}")
        if resource.resources:
            lines.append(
                "- Resources: "
                + ", ".join(f"`{item.resource_id}` ({item.role})" for item in resource.resources)
            )
        lines.extend(["", "## Body", "", resource.body])
        return "\n".join(lines)

    lines = [
        f"# {resource.name}",
        "",
        f"- ID: `{resource.public_id}`",
        f"- Entity type: `{resource.entity_type}`",
        f"- Status: `{resource.status}`",
        f"- Updated: {resource.updated_at}",
    ]
    if resource.aliases:
        lines.append(f"- Aliases: {', '.join(f'`{alias}`' for alias in resource.aliases)}")
    if resource.tags:
        lines.append(f"- Tags: {', '.join(f'`{tag}`' for tag in resource.tags)}")
    lines.extend(["", "## Description", "", resource.description or "_No description provided._"])
    return "\n".join(lines)


def mutation_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Mutation preview" if result.get("dry_run") else "# Mutation result",
        "",
        f"- Dry run: {'yes' if result.get('dry_run') else 'no'}",
        f"- Applied: {'yes' if result.get('applied') else 'no'}",
    ]
    summary = result.get("summary")
    if isinstance(summary, dict) and summary:
        summary_lines = [f"- {key}: {value}" for key, value in summary.items()]
        lines.extend(["", "## Summary", "", *summary_lines])
    impacted = result.get("impacted_resources")
    if isinstance(impacted, list) and impacted:
        lines.extend(["", "## Impacted resources", "", *[f"- `{item}`" for item in impacted]])
    warnings = result.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in warnings:
            if isinstance(warning, dict):
                lines.append(f"- {warning.get('message', pretty_json(warning))}")
            else:
                lines.append(f"- {warning}")
    entry = result.get("entry")
    if entry is not None:
        lines.extend(["", "## Entry", "", f"```json\n{pretty_json(entry)}\n```"])
    edge = result.get("edge")
    if edge is not None:
        lines.extend(["", "## Edge", "", f"```json\n{pretty_json(edge)}\n```"])
    return "\n".join(lines)


def pretty_json(value: Any) -> str:
    return orjson.dumps(value, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS).decode()


def resource_kind(resource: ResourceRecord) -> str:
    if isinstance(resource, EntryRecord):
        return "entry"
    if isinstance(resource, EventRecord):
        return "event"
    return "entity"


def resource_label(resource: ResourceRecord) -> str:
    if isinstance(resource, EntryRecord):
        return resource.title
    if isinstance(resource, EventRecord):
        summary = resource.metadata.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary
        return resource.event_type
    return resource.name


def resource_summary(resource: ResourceRecord) -> str:
    if isinstance(resource, EntryRecord):
        return _first_line(resource.body)
    if isinstance(resource, EventRecord):
        return _first_line(resource.body)
    return resource.description or resource.entity_type


def _short_timestamp(value: str) -> str:
    return value.replace("T", " ")[:19]


def _first_line(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    return stripped.splitlines()[0]


def _truncate(value: str, length: int) -> str:
    if len(value) <= length:
        return value
    return value[: max(length - 1, 1)] + "…"
