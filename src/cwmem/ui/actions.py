from __future__ import annotations

from pathlib import Path
from typing import Any

from cwmem.core.export import (
    render_entry_jsonl,
    render_entry_markdown,
    render_event_jsonl,
)
from cwmem.core.graph import add_edge
from cwmem.core.models import (
    CreateEdgeInput,
    CreateEntryInput,
    EntryRecord,
    EventRecord,
    TagMutationInput,
)
from cwmem.core.safety import execute_mutation
from cwmem.core.store import add_tags, create_entry, remove_tags


def add_entry_action(
    root: Path,
    entry_input: CreateEntryInput,
    *,
    dry_run: bool = False,
    wait_lock: float = 0.0,
) -> dict[str, Any]:
    return execute_mutation(
        root=root,
        command_id="memory.add",
        request_payload={
            "command": "memory.add",
            "input": entry_input.model_dump(mode="json"),
        },
        apply_handler=lambda apply_root: _create_entry_result(apply_root, entry_input),
        summary_builder=lambda _result: {
            "entries_to_create": 1,
            "events_to_create": 1,
        },
        dry_run=dry_run,
        wait_lock=wait_lock,
    )


def mutate_tags_action(
    root: Path,
    mutation_input: TagMutationInput,
    *,
    add: bool,
    dry_run: bool = False,
    wait_lock: float = 0.0,
) -> dict[str, Any]:
    command_id = "memory.tag.add" if add else "memory.tag.remove"
    return execute_mutation(
        root=root,
        command_id=command_id,
        request_payload={
            "command": command_id,
            "input": mutation_input.model_dump(mode="json"),
        },
        apply_handler=lambda apply_root: _tag_result(apply_root, mutation_input, add=add),
        summary_builder=lambda result: {
            "entries_to_update": 1 if result.get("applied") else 0,
            "events_to_create": 1 if result.get("applied") else 0,
        },
        dry_run=dry_run,
        wait_lock=wait_lock,
    )


def link_resources_action(
    root: Path,
    edge_input: CreateEdgeInput,
    *,
    dry_run: bool = False,
    wait_lock: float = 0.0,
) -> dict[str, Any]:
    return execute_mutation(
        root=root,
        command_id="memory.link",
        request_payload={
            "command": "memory.link",
            "input": edge_input.model_dump(mode="json"),
        },
        apply_handler=lambda apply_root: _edge_result(apply_root, edge_input),
        summary_builder=lambda _result: {"edges_to_create": 1},
        dry_run=dry_run,
        wait_lock=wait_lock,
    )


def _create_entry_result(root: Path, entry_input: CreateEntryInput) -> dict[str, Any]:
    entry = create_entry(root, entry_input)
    return {
        "entry": entry,
        "artifacts": {
            "markdown": render_entry_markdown(entry),
            "jsonl": render_entry_jsonl(entry),
        },
    }


def _build_resource_payload(
    resource: EntryRecord | EventRecord, *, applied: bool
) -> dict[str, Any]:
    if isinstance(resource, EntryRecord):
        return {
            "entry": resource,
            "applied": applied,
            "artifacts": {
                "markdown": render_entry_markdown(resource),
                "jsonl": render_entry_jsonl(resource),
            },
        }
    return {
        "event": resource,
        "applied": applied,
        "artifacts": {"jsonl": render_event_jsonl(resource)},
    }


def _tag_result(root: Path, mutation_input: TagMutationInput, *, add: bool) -> dict[str, Any]:
    resource, mutation = (
        add_tags(root, mutation_input) if add else remove_tags(root, mutation_input)
    )
    result = _build_resource_payload(resource, applied=mutation.applied)
    if mutation.applied:
        return result

    result["warnings"] = [
        {
            "code": "WARN_TAG_ALREADY_PRESENT" if add else "WARN_TAG_NOT_FOUND",
            "message": (
                f"Tag(s) already present on resource: {', '.join(mutation_input.tags)}"
                if add
                else f"Tag(s) not found on resource: {', '.join(mutation_input.tags)}"
            ),
            "resource_id": mutation_input.resource_id,
            "tags": mutation_input.tags,
        }
    ]
    return result


def _edge_result(root: Path, edge_input: CreateEdgeInput) -> dict[str, Any]:
    edge = add_edge(root, edge_input)
    return {"edge": edge}
