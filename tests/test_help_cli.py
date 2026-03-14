from __future__ import annotations

import json
from pathlib import Path

from cwmem import __version__


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
    assert "Run lexical and semantic retrieval over memory content." in completed.stdout
    assert "Export or import checked-in collaboration artifacts." in completed.stdout
    assert "deprecate" in completed.stdout.lower()
    assert "not yet implemented" in completed.stdout.lower()
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


def test_version_flag_prints_package_version(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "--version")
    assert completed.returncode == 0, completed
    assert completed.stdout.strip() == __version__
    assert not completed.stderr.strip()
