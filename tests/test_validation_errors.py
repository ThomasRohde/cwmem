from __future__ import annotations

from pathlib import Path

from tests.phase2_helpers import parse_envelope_any_exit


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
