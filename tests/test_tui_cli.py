from __future__ import annotations

import json
from pathlib import Path

from cwmem.cli import tui as tui_module
from tests.helpers import parse_envelope
from tests.phase2_helpers import parse_envelope_any_exit


def test_guide_exposes_tui_as_interactive_command(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "guide")
    payload = parse_envelope(completed.stdout, completed.stderr, completed.returncode)

    result = payload["result"]
    assert isinstance(result, dict), result
    command_catalog = result["command_catalog"]
    assert isinstance(command_catalog, list), command_catalog

    tui_entry = next(item for item in command_catalog if item.get("name") == "tui")
    assert tui_entry["canonical_id"] == "system.tui"
    assert tui_entry["interactive"] is True
    assert tui_entry["requires_tty"] is True
    assert tui_entry["output_schema"] == "InteractiveTerminalSession"

    output_policy = result["output_mode_policy"]
    assert isinstance(output_policy, dict), output_policy
    interactive_commands = output_policy["interactive_commands"]
    assert isinstance(interactive_commands, dict), interactive_commands
    assert "system.tui" in interactive_commands


def test_tui_rejects_noninteractive_launch_with_structured_error(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "tui")
    payload = parse_envelope_any_exit(completed.stdout, completed.stderr)

    assert completed.returncode == 10, completed
    assert payload["ok"] is False, payload
    assert payload["command"] == "system.tui"

    error = payload["errors"][0]
    assert error["code"] == "ERR_VALIDATION_INPUT"
    serialized = json.dumps(error, sort_keys=True).lower()
    assert "tty" in serialized or "llm=true" in serialized


def test_tui_allows_explicit_tty_launch_even_with_llm_true(monkeypatch) -> None:
    class _TTYStream:
        def isatty(self) -> bool:
            return True

    monkeypatch.setenv("LLM", "true")
    monkeypatch.setattr(tui_module.sys, "stdin", _TTYStream())
    monkeypatch.setattr(tui_module.sys, "stdout", _TTYStream())

    tui_module._require_interactive_terminal()
