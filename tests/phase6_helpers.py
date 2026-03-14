from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.phase2_helpers import extract_entry, init_repo, parse_envelope_any_exit, run_ok
from tests.phase3_helpers import select_count

REQUIRED_EXPORT_FILES = (
    Path("memory/entries/entries.jsonl"),
    Path("memory/events/events.jsonl"),
    Path("memory/graph/nodes.jsonl"),
    Path("memory/graph/edges.jsonl"),
    Path("memory/manifests/export-manifest.json"),
)


def run_sync_any(run_cli, tmp_path: Path, *args: str):
    completed = run_cli(tmp_path, *args)
    payload = parse_envelope_any_exit(completed.stdout, completed.stderr)
    _maybe_skip_sync_placeholder(completed, payload, args)
    return completed, payload


def run_sync_ok(run_cli, tmp_path: Path, *args: str) -> dict[str, Any]:
    completed, payload = run_sync_any(run_cli, tmp_path, *args)
    assert completed.returncode == 0, (
        f"Expected success exit code for `cwmem {' '.join(args)}`.\n"
        f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    )
    assert payload["ok"] is True, payload
    return payload


def extract_entity(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    assert isinstance(result, dict), f"Expected object result, got: {type(result)!r}"
    entity = result.get("entity")
    assert isinstance(entity, dict), f"Expected `entity` object, got: {result!r}"
    return entity


def extract_sync_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    assert isinstance(result, dict), f"Expected object result, got: {type(result)!r}"
    return result


def export_memory_snapshot(repo_root: Path) -> dict[str, bytes]:
    memory_root = repo_root / "memory"
    assert memory_root.exists(), f"Expected export root to exist: {memory_root}"
    return {
        path.relative_to(repo_root).as_posix(): path.read_bytes()
        for path in sorted(memory_root.rglob("*"))
        if path.is_file()
    }


def read_manifest(repo_root: Path) -> dict[str, Any]:
    manifest_path = repo_root / "memory" / "manifests" / "export-manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def copy_memory_tree(source_repo: Path, destination_repo: Path) -> None:
    destination_memory = destination_repo / "memory"
    if destination_memory.exists():
        shutil.rmtree(destination_memory)
    shutil.copytree(source_repo / "memory", destination_memory)


def count_records(repo_root: Path) -> dict[str, int]:
    return {
        "entries": select_count(repo_root, "entries"),
        "events": select_count(repo_root, "events"),
        "entities": select_count(repo_root, "entities"),
        "edges": select_count(repo_root, "edges"),
    }


def seed_sync_repo(run_cli, tmp_path: Path) -> dict[str, Any]:
    init_repo(run_cli, tmp_path)

    entity = extract_entity(
        run_ok(
            run_cli,
            tmp_path,
            "entity-add",
            "--entity-type",
            "system",
            "--name",
            "Payments platform",
            "--alias",
            "pay-core",
            "Primary system for sync export fixtures.",
        )
    )

    first_entry = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Deterministic export baseline",
            "--type",
            "decision",
            "--author",
            "alice",
            "--tag",
            "sync",
            "--entity-ref",
            entity["public_id"],
            "Baseline entry body for deterministic sync export coverage.",
        )
    )

    second_entry = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Round trip companion",
            "--type",
            "note",
            "--author",
            "bob",
            "--tag",
            "sync",
            "--entity-ref",
            entity["public_id"],
            "Companion entry keeps graph and artifact exports populated.",
        )
    )

    run_ok(
        run_cli,
        tmp_path,
        "event-add",
        "--event-type",
        "decision.recorded",
        "--summary",
        "Sync export baseline event",
        "--body",
        "Event body used to populate deterministic export fixtures.",
        "--actor",
        "alice",
        "--resource",
        first_entry["public_id"],
    )
    run_ok(
        run_cli,
        tmp_path,
        "link",
        first_entry["public_id"],
        second_entry["public_id"],
        "--relation",
        "supports",
    )
    run_ok(run_cli, tmp_path, "build")

    return {
        "entity": entity,
        "first_entry": first_entry,
        "second_entry": second_entry,
    }


def _maybe_skip_sync_placeholder(completed, payload: dict[str, Any], args: tuple[str, ...]) -> None:
    errors = payload.get("errors", [])
    error_codes = {error.get("code") for error in errors if isinstance(error, dict)}
    is_placeholder_response = (
        completed.returncode == 10
        and payload.get("ok") is False
        and error_codes == {"ERR_NOT_IMPLEMENTED"}
    )
    if is_placeholder_response:
        pytest.skip(
            "Phase 6 sync implementation is not landed yet. "
            "These tests define the CLI contract and should pass once e6-sync-code exists.\n"
            f"Skipped while running: cwmem {' '.join(args)}"
        )
