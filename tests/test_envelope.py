from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import assert_required_envelope_keys, parse_envelope


@pytest.mark.parametrize(
    ("command_args", "expected_command"),
    [
        (("guide",), "system.guide"),
        (("status",), "system.status"),
        (("init",), "system.init"),
    ],
)
def test_bootstrap_commands_emit_required_envelope_keys(
    run_cli, tmp_path: Path, command_args: tuple[str, ...], expected_command: str
) -> None:
    completed = run_cli(tmp_path, *command_args)
    payload = parse_envelope(completed.stdout, completed.stderr, completed.returncode)

    assert_required_envelope_keys(payload)
    assert payload["ok"] is True
    assert payload["command"] == expected_command

