from __future__ import annotations

from pathlib import Path

from tests.helpers import parse_envelope


def test_guide_exposes_gui_as_interactive_command(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "guide")
    payload = parse_envelope(completed.stdout, completed.stderr, completed.returncode)

    result = payload["result"]
    assert isinstance(result, dict), result
    command_catalog = result["command_catalog"]
    assert isinstance(command_catalog, list), command_catalog

    gui_entry = next(item for item in command_catalog if item.get("name") == "gui")
    assert gui_entry["canonical_id"] == "system.gui"
    assert gui_entry["interactive"] is True
    assert gui_entry["requires_tty"] is False
    assert gui_entry["output_schema"] == "InteractiveWebSession"

    output_policy = result["output_mode_policy"]
    assert isinstance(output_policy, dict), output_policy
    interactive_commands = output_policy["interactive_commands"]
    assert isinstance(interactive_commands, dict), interactive_commands
    assert "system.gui" in interactive_commands
