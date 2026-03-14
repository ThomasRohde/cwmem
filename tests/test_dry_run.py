from __future__ import annotations

import json
from pathlib import Path

from tests.phase2_helpers import extract_entries, extract_entry, init_repo, run_ok
from tests.phase3_helpers import select_count
from tests.phase6_helpers import REQUIRED_EXPORT_FILES, run_sync_ok, seed_sync_repo
from tests.phase7_helpers import run_phase7_ok


def _assert_dry_run_result(payload: dict[str, object]) -> dict[str, object]:
    result = payload.get("result")
    assert isinstance(result, dict), result
    assert result.get("dry_run", payload.get("dry_run")) is True, payload

    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "dry_run" in serialized
    assert any(
        token in serialized for token in ("summary", "changes", "proposed", "impacted", "plan")
    ), payload
    return result


def test_add_dry_run_reports_changes_without_persisting_entry_or_events(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)
    before_counts = {
        "entries": select_count(tmp_path, "entries"),
        "events": select_count(tmp_path, "events"),
    }

    payload = run_phase7_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Dry-run add",
        "--type",
        "note",
        "--dry-run",
        "This should not persist.",
        missing_option_names=("--dry-run",),
    )

    assert payload["command"] == "memory.add"
    _assert_dry_run_result(payload)
    assert select_count(tmp_path, "entries") == before_counts["entries"]
    assert select_count(tmp_path, "events") == before_counts["events"]

    list_payload = run_ok(run_cli, tmp_path, "list")
    assert extract_entries(list_payload) == []


def test_update_dry_run_preserves_entry_content_and_fingerprint(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)
    created_entry = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Dry-run update target",
            "--type",
            "note",
            "Original content stays in place.",
        )
    )
    before_events = select_count(tmp_path, "events")

    payload = run_phase7_ok(
        run_cli,
        tmp_path,
        "update",
        created_entry["public_id"],
        "--expected-fingerprint",
        created_entry["fingerprint"],
        "--title",
        "Dry-run update candidate",
        "--dry-run",
        missing_option_names=("--dry-run",),
    )

    assert payload["command"] == "memory.update"
    _assert_dry_run_result(payload)

    refreshed_entry = extract_entry(run_ok(run_cli, tmp_path, "get", created_entry["public_id"]))
    assert refreshed_entry["title"] == created_entry["title"]
    assert refreshed_entry["fingerprint"] == created_entry["fingerprint"]
    assert select_count(tmp_path, "events") == before_events


def test_sync_export_dry_run_can_emit_plan_without_writing_export_surface(
    run_cli, tmp_path: Path
) -> None:
    seed_sync_repo(run_cli, tmp_path)
    before_counts = {
        "entries": select_count(tmp_path, "entries"),
        "events": select_count(tmp_path, "events"),
    }
    plan_path = tmp_path / ".cwmem" / "plans" / "export-plan.json"
    exported_entries = tmp_path / "memory" / "entries" / "entries.jsonl"
    exported_manifest = tmp_path / "memory" / "manifests" / "export-manifest.json"

    assert not exported_entries.exists()
    assert not exported_manifest.exists()

    payload = run_phase7_ok(
        run_cli,
        tmp_path,
        "sync",
        "export",
        "--dry-run",
        "--plan-out",
        str(plan_path),
        missing_option_names=("--dry-run", "--plan-out"),
    )

    assert payload["command"] == "memory.sync.export"
    _assert_dry_run_result(payload)
    assert plan_path.is_file()
    assert select_count(tmp_path, "entries") == before_counts["entries"]
    assert select_count(tmp_path, "events") == before_counts["events"]
    assert not exported_entries.exists()
    assert not exported_manifest.exists()

    run_sync_ok(run_cli, tmp_path, "sync", "export")
    for relative_path in REQUIRED_EXPORT_FILES:
        assert (tmp_path / relative_path).exists(), relative_path
