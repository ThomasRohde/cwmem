from __future__ import annotations

import json
from pathlib import Path

from tests.phase2_helpers import init_repo
from tests.phase6_helpers import (
    copy_memory_tree,
    count_records,
    run_sync_any,
    run_sync_ok,
    seed_sync_repo,
)
from tests.phase7_helpers import run_phase7_any, run_phase7_ok


def _assert_verify_problem(completed, payload: dict[str, object]) -> str:
    assert payload["command"] == "system.verify"
    assert completed.returncode == 10, (
        "Verify failures should map to the validation exit code.\n"
        f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    )
    assert payload["ok"] is False, payload

    errors = payload.get("errors")
    assert isinstance(errors, list) and errors, payload
    first_error = errors[0]
    assert isinstance(first_error, dict), errors
    assert first_error.get("code") == "ERR_VALIDATION_INPUT", first_error

    details = first_error.get("details")
    assert isinstance(details, dict), first_error
    issues = details.get("issues")
    if issues is not None:
        assert isinstance(issues, list) and issues, details

    return json.dumps(payload, sort_keys=True).lower()


def _assert_import_problem(completed, payload: dict[str, object]) -> str:
    assert payload["command"] == "memory.sync.import"

    result = payload.get("result")
    is_result_problem = isinstance(result, dict) and result.get("ok") is False
    assert payload["ok"] is False or is_result_problem, payload

    if payload["ok"] is False:
        assert completed.returncode == 10, (
            "Import validation failures should map to the validation exit code.\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    else:
        assert completed.returncode == 0, completed

    return json.dumps(payload, sort_keys=True).lower()


def test_verify_succeeds_on_consistent_repository_surface(run_cli, tmp_path: Path) -> None:
    seed_sync_repo(run_cli, tmp_path)
    run_sync_ok(run_cli, tmp_path, "sync", "export")

    payload = run_phase7_ok(run_cli, tmp_path, "verify")
    assert payload["command"] == "system.verify"

    result = payload["result"]
    assert isinstance(result, dict), result
    if "ok" in result:
        assert result["ok"] is True
    for key in ("valid", "verified", "healthy"):
        if key in result:
            assert result[key] is True
    issues = result.get("issues")
    if issues is not None:
        assert issues == []


def test_verify_reports_problem_after_export_artifact_tamper(
    run_cli, tmp_path: Path
) -> None:
    seed_sync_repo(run_cli, tmp_path)
    run_sync_ok(run_cli, tmp_path, "sync", "export")

    entries_jsonl = tmp_path / "memory" / "entries" / "entries.jsonl"
    entries_jsonl.write_text(entries_jsonl.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    completed, payload = run_phase7_any(run_cli, tmp_path, "verify")
    serialized = _assert_verify_problem(completed, payload)
    assert any(
        token in serialized
        for token in ("export", "manifest", "fingerprint", "stale", "drift", "mismatch")
    ), payload


def test_sync_import_rejects_tampered_artifacts_without_writing_sqlite(
    run_cli, tmp_path: Path
) -> None:
    source_repo = tmp_path / "source"
    destination_repo = tmp_path / "destination"
    source_repo.mkdir()
    destination_repo.mkdir()

    seed_sync_repo(run_cli, source_repo)
    run_sync_ok(run_cli, source_repo, "sync", "export")

    init_repo(run_cli, destination_repo)
    copy_memory_tree(source_repo, destination_repo)
    before_counts = count_records(destination_repo)

    entries_jsonl = destination_repo / "memory" / "entries" / "entries.jsonl"
    entries_jsonl.write_text(entries_jsonl.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    completed, payload = run_sync_any(run_cli, destination_repo, "sync", "import")
    serialized = _assert_import_problem(completed, payload)

    assert count_records(destination_repo) == before_counts
    assert any(
        token in serialized for token in ("artifact", "manifest", "fingerprint", "mismatch")
    ), payload
