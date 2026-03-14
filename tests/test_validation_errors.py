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
