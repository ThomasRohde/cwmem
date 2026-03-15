from __future__ import annotations

import json
from pathlib import Path

from cwmem import __version__
from tests.phase2_helpers import parse_envelope_any_exit


def _assert_human_help(completed) -> None:
    assert completed.returncode == 0, completed
    assert "Usage:" in completed.stdout
    assert "Options:" in completed.stdout
    assert "Commands:" in completed.stdout
    assert "--version" in completed.stdout
    assert "cwmem stores repository-scoped memory next to your codebase" in completed.stdout
    assert "Typical flow:" in completed.stdout
    assert "Return machine-readable CLI documentation." in completed.stdout
    assert "Create runtime and tracked repository scaffolding." in completed.stdout
    assert "Install the bundled cwmem skill into the current repository." in completed.stdout
    assert "Run lexical and semantic retrieval over memory content." in completed.stdout
    assert "Export or import checked-in collaboration artifacts." in completed.stdout
    assert "deprecate" not in completed.stdout.lower()
    assert "Ôö" not in completed.stdout
    try:
        json.loads(completed.stdout)
    except json.JSONDecodeError:
        return
    raise AssertionError(f"Expected human-readable help, got JSON:\n{completed.stdout}")


def test_no_args_print_human_help(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path)
    _assert_human_help(completed)


def test_help_flag_prints_human_help(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "--help")
    _assert_human_help(completed)


def test_deprecate_help_calls_out_not_yet_implemented(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "deprecate", "--help")
    assert completed.returncode == 0, completed
    assert "not yet implemented" in completed.stdout.lower()
    assert "deprecate a memory item while preserving history" in completed.stdout.lower()
    assert "Ôö" not in completed.stdout


def test_deprecate_placeholder_accepts_resource_id_and_returns_not_implemented(
    run_cli, tmp_path: Path
) -> None:
    completed = run_cli(tmp_path, "deprecate", "mem-000001")
    payload = parse_envelope_any_exit(completed.stdout, completed.stderr)

    assert completed.returncode == 90, completed
    assert payload["ok"] is False, payload
    assert payload["command"] == "memory.deprecate"
    assert [error["code"] for error in payload["errors"]] == ["ERR_NOT_IMPLEMENTED"]
    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "mem-000001" in serialized
    assert "not implemented" in serialized


def test_subcommand_help_uses_readable_option_spacing(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "add", "--help")
    assert completed.returncode == 0, completed
    assert "--title TEXT" in completed.stdout
    assert "--cwd PATH" in completed.stdout
    assert "--titleTEXT" not in completed.stdout
    assert "--cwdPATH" not in completed.stdout
    assert "--help-h" not in completed.stdout


def test_plan_help_lists_supported_workflows(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "plan", "--help")
    assert completed.returncode == 0, completed
    lowered = completed.stdout.lower()
    assert "sync-export" in lowered
    assert "sync-import" in lowered
    assert "bootstrap" in lowered


def test_verify_help_mentions_build_and_sync_export(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "verify", "--help")
    assert completed.returncode == 0, completed
    lowered = completed.stdout.lower()
    assert "cwmem build" in lowered
    assert "cwmem sync export" in lowered


def test_skill_help_mentions_auto_detection_and_recommendations(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "skill", "--help")
    assert completed.returncode == 0, completed
    lowered = completed.stdout.lower()
    assert "--target" in completed.stdout
    assert "--strategy" in completed.stdout
    assert "--idempotency-key" in completed.stdout
    assert ".agents/skills/cwmem" in lowered
    assert "without editing" in lowered
    assert "automatically" in lowered


def test_version_flags_print_package_version(run_cli, tmp_path: Path) -> None:
    for flag in ("--version", "-V", "-v"):
        completed = run_cli(tmp_path, flag)
        assert completed.returncode == 0, completed
        assert completed.stdout.strip() == __version__
        assert not completed.stderr.strip()
