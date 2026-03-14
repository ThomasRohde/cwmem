from __future__ import annotations

import json
from pathlib import Path

from tests.phase6_helpers import (
    REQUIRED_EXPORT_FILES,
    export_memory_snapshot,
    read_manifest,
    run_sync_any,
    run_sync_ok,
    seed_sync_repo,
)


def _assert_successful_check(payload: dict[str, object]) -> None:
    assert payload["command"] == "memory.sync.export"
    result = payload.get("result")
    assert isinstance(result, dict), result
    if "ok" in result:
        assert result["ok"] is True
    if "status" in result:
        assert result["status"] in {"ok", "clean", "fresh"}


def _assert_stale_check(completed, payload: dict[str, object]) -> None:
    assert payload["command"] == "memory.sync.export"
    result = payload.get("result")
    result_failed = isinstance(result, dict) and result.get("ok") is False
    assert completed.returncode != 0 or payload["ok"] is False or result_failed, payload

    serialized = json.dumps(payload, sort_keys=True).lower()
    assert any(token in serialized for token in ("stale", "drift", "mismatch", "conflict")), payload


def test_sync_export_writes_expected_artifact_surface_deterministically(
    run_cli, tmp_path: Path
) -> None:
    seed_sync_repo(run_cli, tmp_path)

    first_export = run_sync_ok(run_cli, tmp_path, "sync", "export")
    assert first_export["command"] == "memory.sync.export"

    for relative_path in REQUIRED_EXPORT_FILES:
        assert (tmp_path / relative_path).exists(), relative_path

    entry_markdown_files = sorted((tmp_path / "memory" / "entries").glob("*.md"))
    assert entry_markdown_files, "Expected one markdown artifact per entry."

    first_snapshot = export_memory_snapshot(tmp_path)
    manifest = read_manifest(tmp_path)
    files = manifest.get("files")
    assert isinstance(files, dict), manifest
    for relative_path in REQUIRED_EXPORT_FILES:
        normalized = relative_path.relative_to("memory").as_posix()
        assert normalized in files, files

    second_export = run_sync_ok(run_cli, tmp_path, "sync", "export")
    assert second_export["command"] == "memory.sync.export"
    second_snapshot = export_memory_snapshot(tmp_path)
    assert second_snapshot == first_snapshot


def test_sync_export_check_detects_stale_artifacts(run_cli, tmp_path: Path) -> None:
    seed_sync_repo(run_cli, tmp_path)

    run_sync_ok(run_cli, tmp_path, "sync", "export")
    completed, payload = run_sync_any(run_cli, tmp_path, "sync", "export", "--check")
    assert completed.returncode == 0, completed
    _assert_successful_check(payload)

    entries_jsonl = tmp_path / "memory" / "entries" / "entries.jsonl"
    entries_jsonl.write_text(entries_jsonl.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    completed, payload = run_sync_any(run_cli, tmp_path, "sync", "export", "--check")
    _assert_stale_check(completed, payload)
