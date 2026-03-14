from __future__ import annotations

from pathlib import Path

from tests.helpers import assert_required_envelope_keys, parse_envelope


def test_init_is_idempotent_and_creates_expected_paths(run_cli, tmp_path: Path) -> None:
    first_result = run_cli(tmp_path, "init")
    second_result = run_cli(tmp_path, "init")
    first = parse_envelope(first_result.stdout, first_result.stderr, first_result.returncode)
    second = parse_envelope(second_result.stdout, second_result.stderr, second_result.returncode)

    assert_required_envelope_keys(first)
    assert_required_envelope_keys(second)
    assert first["command"] == "system.init"
    assert second["command"] == "system.init"
    assert first["ok"] is True
    assert second["ok"] is True

    assert (tmp_path / ".cwmem").is_dir()
    assert (tmp_path / "memory").is_dir()
    assert (tmp_path / "models" / "model2vec").is_dir()


def test_status_distinguishes_uninitialized_and_initialized_repos(run_cli, tmp_path: Path) -> None:
    before_result = run_cli(tmp_path, "status")
    init_result = run_cli(tmp_path, "init")
    after_result = run_cli(tmp_path, "status")
    before = parse_envelope(before_result.stdout, before_result.stderr, before_result.returncode)
    init_payload = parse_envelope(init_result.stdout, init_result.stderr, init_result.returncode)
    after = parse_envelope(after_result.stdout, after_result.stderr, after_result.returncode)

    assert_required_envelope_keys(before)
    assert_required_envelope_keys(init_payload)
    assert_required_envelope_keys(after)

    assert before["command"] == "system.status"
    assert init_payload["command"] == "system.init"
    assert after["command"] == "system.status"

    assert before["result"]["initialized"] is False
    assert after["result"]["initialized"] is True
