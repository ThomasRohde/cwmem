from __future__ import annotations

import json
from pathlib import Path


def _assert_human_help(completed) -> None:
    assert completed.returncode == 0, completed
    assert "Usage:" in completed.stdout
    assert "Repo-native institutional memory CLI." in completed.stdout
    assert "guide" in completed.stdout
    assert "status" in completed.stdout
    assert "sync" in completed.stdout
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
