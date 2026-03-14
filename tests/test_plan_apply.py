from __future__ import annotations

import json
from pathlib import Path

from tests.phase2_helpers import run_any, run_ok
from tests.phase6_helpers import REQUIRED_EXPORT_FILES, seed_sync_repo


def test_plan_validate_apply_export_workflow_creates_reviewable_artifacts(
    run_cli, tmp_path: Path
) -> None:
    seed_sync_repo(run_cli, tmp_path)
    plan_path = tmp_path / ".cwmem" / "plans" / "export-plan.json"

    plan_payload = run_ok(
        run_cli,
        tmp_path,
        "plan",
        "sync-export",
        "--plan-out",
        str(plan_path),
    )
    assert plan_payload["command"] == "system.plan"
    assert plan_path.is_file()

    validate_payload = run_ok(run_cli, tmp_path, "validate", "--plan", str(plan_path))
    assert validate_payload["command"] == "system.validate"
    validate_result = validate_payload["result"]
    assert isinstance(validate_result, dict), validate_result
    assert validate_result.get("ok") is True

    apply_payload = run_ok(run_cli, tmp_path, "apply", "--plan", str(plan_path))
    assert apply_payload["command"] == "system.apply"
    for relative_path in REQUIRED_EXPORT_FILES:
        assert (tmp_path / relative_path).exists(), relative_path


def test_validate_plan_reports_state_drift_after_repository_changes(
    run_cli, tmp_path: Path
) -> None:
    seed_sync_repo(run_cli, tmp_path)
    plan_path = tmp_path / ".cwmem" / "plans" / "export-plan.json"

    run_ok(
        run_cli,
        tmp_path,
        "plan",
        "sync-export",
        "--plan-out",
        str(plan_path),
    )
    run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Plan drift entry",
        "--type",
        "note",
        "Changing the repository should invalidate the saved export plan.",
    )

    completed, payload = run_any(run_cli, tmp_path, "validate", "--plan", str(plan_path))
    assert payload["command"] == "system.validate"
    assert completed.returncode == 0, completed

    result = payload["result"]
    assert isinstance(result, dict), result
    assert result.get("ok") is False

    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "plan" in serialized
    assert any(token in serialized for token in ("drift", "mismatch", "state")), payload
