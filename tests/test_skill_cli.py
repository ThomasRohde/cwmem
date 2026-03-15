from __future__ import annotations

from pathlib import Path

from cwmem.core.skills import authoring_skill_root, bundled_skill_files, bundled_skill_root
from tests.helpers import parse_envelope
from tests.phase2_helpers import parse_envelope_any_exit


def test_skill_dry_run_defaults_to_agents_when_no_customizations_exist(
    run_cli, tmp_path: Path
) -> None:
    completed = run_cli(tmp_path, "skill", "--dry-run")
    payload = parse_envelope(completed.stdout, completed.stderr, completed.returncode)

    assert payload["command"] == "system.skill.install"
    result = payload["result"]
    assert result["dry_run"] is True
    assert result["applied"] is False
    assert result["defaulted_to_agents"] is True
    assert [target["path"] for target in result["resolved_targets"]] == [".agents/skills/cwmem"]
    assert ".agents/skills/cwmem/SKILL.md" in result["written_files"]
    assert ".agents/skills/cwmem/references/commands.md" in result["written_files"]
    assert result["recommendations"][0]["path"] == "AGENTS.md"
    assert not (tmp_path / ".agents" / "skills" / "cwmem").exists()


def test_skill_auto_installs_to_detected_copilot_and_claude_surfaces(
    run_cli, tmp_path: Path
) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "copilot-instructions.md").write_text(
        "Use repo skills.\n",
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text("Claude instructions.\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Generic agent instructions.\n", encoding="utf-8")

    completed = run_cli(tmp_path, "skill")
    payload = parse_envelope(completed.stdout, completed.stderr, completed.returncode)

    result = payload["result"]
    assert result["defaulted_to_agents"] is False
    assert [target["path"] for target in result["resolved_targets"]] == [
        ".github/skills/cwmem",
        ".claude/skills/cwmem",
    ]

    assert (tmp_path / ".github" / "skills" / "cwmem" / "SKILL.md").is_file()
    assert (tmp_path / ".github" / "skills" / "cwmem" / "references" / "commands.md").is_file()
    assert (tmp_path / ".claude" / "skills" / "cwmem" / "SKILL.md").is_file()
    assert (tmp_path / ".claude" / "skills" / "cwmem" / "references" / "commands.md").is_file()

    recommendation_paths = [item["path"] for item in result["recommendations"]]
    assert recommendation_paths == [
        "AGENTS.md",
        ".github/copilot-instructions.md",
        "CLAUDE.md",
    ]


def test_skill_install_replays_success_for_same_idempotency_key(run_cli, tmp_path: Path) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "copilot-instructions.md").write_text(
        "Use repo skills.\n",
        encoding="utf-8",
    )

    first = run_cli(tmp_path, "skill", "--idempotency-key", "skill-install-demo")
    first_payload = parse_envelope(first.stdout, first.stderr, first.returncode)

    second = run_cli(tmp_path, "skill", "--idempotency-key", "skill-install-demo")
    second_payload = parse_envelope(second.stdout, second.stderr, second.returncode)

    assert first_payload["result"]["written_files"] == second_payload["result"]["written_files"]
    assert second_payload["result"]["idempotency"]["replayed"] is True
    assert second_payload["result"]["idempotency"]["idempotency_key"] == "skill-install-demo"


def test_skill_install_rejects_conflicting_existing_files_without_force(
    run_cli, tmp_path: Path
) -> None:
    (tmp_path / ".github" / "skills" / "cwmem").mkdir(parents=True)
    (tmp_path / ".github" / "copilot-instructions.md").write_text(
        "Use repo skills.\n",
        encoding="utf-8",
    )
    conflicting_path = tmp_path / ".github" / "skills" / "cwmem" / "SKILL.md"
    conflicting_path.write_text("conflicting skill payload\n", encoding="utf-8")

    completed = run_cli(tmp_path, "skill")
    payload = parse_envelope_any_exit(completed.stdout, completed.stderr)

    assert completed.returncode == 40, completed
    assert payload["ok"] is False, payload
    assert payload["errors"][0]["code"] == "ERR_CONFLICT_STATE"
    assert conflicting_path.read_text(encoding="utf-8") == "conflicting skill payload\n"


def test_bundled_skill_assets_match_authoring_source() -> None:
    source_root = authoring_skill_root()
    assert source_root is not None

    bundled_root = bundled_skill_root()
    bundled_files = bundled_skill_files()
    source_files = sorted(
        path.relative_to(source_root)
        for path in source_root.rglob("*")
        if path.is_file()
    )

    assert bundled_files == source_files
    for relative in bundled_files:
        assert (bundled_root / relative).read_bytes() == (source_root / relative).read_bytes()
