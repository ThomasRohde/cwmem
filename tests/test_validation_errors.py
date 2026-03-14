from __future__ import annotations

import json
from pathlib import Path

from tests.phase2_helpers import init_repo, parse_envelope_any_exit, run_any


def test_click_usage_errors_emit_validation_envelopes(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "tag-add", "mem-000001")
    payload = parse_envelope_any_exit(completed.stdout, completed.stderr)

    assert completed.returncode == 10, (
        "CLI usage and validation errors should map to validation envelopes.\n"
        f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    )
    assert payload["ok"] is False
    assert payload["command"] == "system.cli"
    assert [error["code"] for error in payload["errors"]] == ["ERR_VALIDATION_INPUT"]


def test_validate_and_apply_reject_malformed_plan_files_as_validation_errors(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)
    plan_cases = [
        ("empty-plan.json", "", "empty"),
        ("whitespace-plan.json", "  \n\t  ", "whitespace"),
        ("invalid-plan.json", "not valid json", "json"),
    ]

    for file_name, content, expected_token in plan_cases:
        plan_path = tmp_path / file_name
        plan_path.write_text(content, encoding="utf-8")

        for command_name in ("validate", "apply"):
            completed, payload = run_any(
                run_cli,
                tmp_path,
                command_name,
                "--plan",
                str(plan_path),
            )
            assert completed.returncode == 10, completed
            assert payload["ok"] is False, payload
            assert payload["command"] == f"system.{command_name}"
            assert [error["code"] for error in payload["errors"]] == ["ERR_VALIDATION_INPUT"]

            serialized = json.dumps(payload, sort_keys=True).lower()
            assert expected_token in serialized, payload
            assert "err_internal_unhandled" not in serialized, payload


def test_validate_and_apply_reject_non_utf8_and_schema_invalid_plan_files(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)
    binary_plan = tmp_path / "binary-plan.bin"
    binary_plan.write_bytes(bytes(range(256)))
    schema_plan = tmp_path / "schema-plan.json"
    schema_plan.write_text('{"workflow":"sync.export"}', encoding="utf-8")

    cases = [
        (binary_plan, "utf-8"),
        (schema_plan, "schema"),
    ]

    for plan_path, expected_token in cases:
        for command_name in ("validate", "apply"):
            completed, payload = run_any(
                run_cli,
                tmp_path,
                command_name,
                "--plan",
                str(plan_path),
            )
            assert completed.returncode == 10, completed
            assert payload["ok"] is False, payload
            assert payload["command"] == f"system.{command_name}"
            assert [error["code"] for error in payload["errors"]] == ["ERR_VALIDATION_INPUT"]

            serialized = json.dumps(payload, sort_keys=True).lower()
            assert expected_token in serialized, payload
            assert "err_internal_unhandled" not in serialized, payload


def test_duplicate_scalar_options_emit_validation_envelopes(run_cli, tmp_path: Path) -> None:
    completed, payload = run_any(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "first",
        "--title",
        "second",
        "Duplicate title body",
    )

    assert completed.returncode == 10, completed
    assert payload["ok"] is False, payload
    assert payload["command"] == "system.cli"
    assert [error["code"] for error in payload["errors"]] == ["ERR_VALIDATION_INPUT"]

    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "duplicate" in serialized
    assert "--title" in serialized


def test_add_rejects_empty_title(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)
    completed, payload = run_any(
        run_cli, tmp_path, "add", "--title", "", "Some body content"
    )
    assert completed.returncode == 10, completed
    assert payload["ok"] is False
    assert [e["code"] for e in payload["errors"]] == ["ERR_VALIDATION_INPUT"]
    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "title" in serialized


def test_add_rejects_whitespace_only_body(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)
    completed, payload = run_any(
        run_cli, tmp_path, "add", "--title", "Valid title", "   "
    )
    assert completed.returncode == 10, completed
    assert payload["ok"] is False
    assert [e["code"] for e in payload["errors"]] == ["ERR_VALIDATION_INPUT"]
    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "body" in serialized


def test_event_add_rejects_invalid_occurred_at(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)
    completed, payload = run_any(
        run_cli,
        tmp_path,
        "event-add",
        "--event-type",
        "meeting",
        "--occurred-at",
        "not-a-date",
        "Test event body",
    )
    assert completed.returncode == 10, completed
    assert payload["ok"] is False
    assert [e["code"] for e in payload["errors"]] == ["ERR_VALIDATION_INPUT"]
    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "occurred-at" in serialized or "iso 8601" in serialized


def test_event_add_accepts_valid_iso8601_occurred_at(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)
    completed, payload = run_any(
        run_cli,
        tmp_path,
        "event-add",
        "--event-type",
        "meeting",
        "--occurred-at",
        "2025-06-15T10:00:00+00:00",
        "Valid date event",
    )
    assert completed.returncode == 0, completed
    assert payload["ok"] is True


def test_tag_add_noop_emits_warning(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)
    run_any(
        run_cli, tmp_path, "add", "--title", "Tag test", "Body for tag test"
    )
    run_any(run_cli, tmp_path, "tag-add", "mem-000001", "--tag", "mytag")
    # Add same tag again — should succeed with warning
    completed, payload = run_any(
        run_cli, tmp_path, "tag-add", "mem-000001", "--tag", "mytag"
    )
    assert completed.returncode == 0, completed
    assert payload["ok"] is True
    assert payload["result"]["applied"] is False
    assert len(payload["warnings"]) >= 1
    assert any(w["code"] == "WARN_TAG_ALREADY_PRESENT" for w in payload["warnings"])


def test_tag_remove_noop_emits_warning(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)
    run_any(
        run_cli, tmp_path, "add", "--title", "Tag test", "Body for tag test"
    )
    # Remove a tag that doesn't exist — should succeed with warning
    completed, payload = run_any(
        run_cli, tmp_path, "tag-remove", "mem-000001", "--tag", "nonexistent"
    )
    assert completed.returncode == 0, completed
    assert payload["ok"] is True
    assert payload["result"]["applied"] is False
    assert len(payload["warnings"]) >= 1
    assert any(w["code"] == "WARN_TAG_NOT_FOUND" for w in payload["warnings"])


def test_deprecate_returns_internal_exit_code(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "deprecate", "mem-000001")
    payload = parse_envelope_any_exit(completed.stdout, completed.stderr)
    assert completed.returncode == 90, (
        f"ERR_NOT_IMPLEMENTED should map to exit code 90 (internal), not 10.\n"
        f"STDOUT:\n{completed.stdout}"
    )
    assert [e["code"] for e in payload["errors"]] == ["ERR_NOT_IMPLEMENTED"]


def test_add_accepts_body_via_body_flag(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)
    completed, payload = run_any(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Body flag test",
        "--body",
        "Content via --body flag",
    )
    assert completed.returncode == 0, completed
    assert payload["ok"] is True
    entry = payload["result"]["entry"]
    assert entry["body"] == "Content via --body flag"
