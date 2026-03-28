"""Integration tests for the JSONL merge driver within actual git merges.

These tests create real git repositories, branch, add records on both
sides, configure the cwmem merge driver, and verify that ``git merge``
resolves JSONL conflicts automatically.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import SRC_ROOT
from tests.phase2_helpers import extract_entry, init_repo, run_ok
from tests.phase6_helpers import run_sync_ok


def _git(
    repo: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=check,
    )


def _python_path_for_git() -> str:
    """Python path compatible with git's MSYS2 bash on Windows."""
    return sys.executable.replace("\\", "/")


def _add_and_commit(repo: Path, msg: str) -> None:
    """Stage tracked memory artifacts and commit."""
    _git(repo, "add", "memory/", ".gitignore", ".gitattributes")
    _git(repo, "commit", "-m", msg, "--allow-empty")


def _configure_merge_driver(repo: Path) -> None:
    """Configure the cwmem JSONL merge driver for a test repo."""
    ga = repo / ".gitattributes"
    lines = ga.read_text(encoding="utf-8") if ga.exists() else ""
    if "merge=cwmem-jsonl" not in lines:
        new = lines.rstrip("\n") + "\nmemory/**/*.jsonl merge=cwmem-jsonl\n"
        ga.write_text(new, encoding="utf-8")

    _git(
        repo, "config", "--local",
        "merge.cwmem-jsonl.name", "cwmem JSONL union merge",
    )
    python = _python_path_for_git()
    src = str(SRC_ROOT).replace("\\", "/")
    driver_cmd = (
        f"PYTHONPATH='{src}' {python}"
        " -m cwmem merge-driver %O %A %B %L %P"
    )
    _git(
        repo, "config", "--local",
        "merge.cwmem-jsonl.driver", driver_cmd,
    )


def _unconfigure_merge_driver(repo: Path) -> None:
    """Remove the merge driver so conflicts fall through to markers."""
    _git(
        repo, "config", "--local",
        "--remove-section", "merge.cwmem-jsonl",
        check=False,
    )
    ga = repo / ".gitattributes"
    if ga.is_file():
        lines = ga.read_text(encoding="utf-8").splitlines()
        filtered = [
            line for line in lines
            if "merge=cwmem-jsonl" not in line
        ]
        ga.write_text("\n".join(filtered) + "\n", encoding="utf-8")


def _ensure_cwmem_gitignored(repo: Path) -> None:
    """Ensure .cwmem/ is gitignored to avoid binary sqlite conflicts."""
    gi = repo / ".gitignore"
    content = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    if ".cwmem/" not in content:
        if not content.endswith("\n"):
            content += "\n"
        content += ".cwmem/\n"
        gi.write_text(content, encoding="utf-8")


def _init_test_repo(run_cli, path: Path) -> None:
    """Create a git + cwmem repo with .cwmem/ gitignored."""
    _git(path, "init")
    _git(path, "config", "user.email", "test@test.com")
    _git(path, "config", "user.name", "Test")
    init_repo(run_cli, path)
    _ensure_cwmem_gitignored(path)


def _read_jsonl(path: Path) -> list[dict]:
    """Read all records from a JSONL file."""
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _assert_no_conflict_markers(repo: Path) -> None:
    """Assert no JSONL files contain git conflict markers."""
    for jsonl in (repo / "memory").rglob("*.jsonl"):
        content = jsonl.read_text(encoding="utf-8")
        assert "<<<<<<<" not in content, (
            f"Conflict markers in {jsonl.name}"
        )


class TestMergeDriverGitIntegration:
    """Full git merge integration tests."""

    def test_both_branches_add_events_merge_clean(
        self, run_cli, tmp_path: Path,
    ) -> None:
        """Two branches each add an event. Driver merges cleanly."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_test_repo(run_cli, repo)
        _configure_merge_driver(repo)

        entry = extract_entry(
            run_ok(
                run_cli, repo,
                "add", "--title", "Baseline", "--type", "note",
                "Baseline body",
            )
        )
        run_sync_ok(run_cli, repo, "sync", "export")
        _add_and_commit(repo, "baseline")

        # Branch A: add event
        _git(repo, "checkout", "-b", "branch-a")
        run_ok(
            run_cli, repo,
            "event-add", "--event-type", "review.completed",
            "--summary", "Event from branch A",
            "--body", "Branch A event body",
            "--actor", "alice",
            "--resource", entry["public_id"],
        )
        run_sync_ok(run_cli, repo, "sync", "export")
        _add_and_commit(repo, "branch-a event")

        # Back to master: add different event
        _git(repo, "checkout", "master")
        run_ok(
            run_cli, repo,
            "event-add", "--event-type", "status.changed",
            "--summary", "Event from branch B",
            "--body", "Branch B event body",
            "--actor", "bob",
            "--resource", entry["public_id"],
        )
        run_sync_ok(run_cli, repo, "sync", "export")
        _add_and_commit(repo, "master event")

        # Merge — driver should handle JSONL conflicts
        result = _git(
            repo, "merge", "branch-a", "-m", "merge",
            check=False,
        )
        assert result.returncode == 0, (
            f"Merge failed!\nSTDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

        _assert_no_conflict_markers(repo)

        # Both events present in merged events.jsonl
        events = _read_jsonl(
            repo / "memory" / "events" / "events.jsonl"
        )
        bodies = {
            e.get("summary", "") + " " + e.get("body", "")
            for e in events
        }
        all_text = " ".join(bodies).lower()
        assert "branch a" in all_text, (
            f"Branch A event missing. Events: {bodies}"
        )
        assert "branch b" in all_text, (
            f"Branch B event missing. Events: {bodies}"
        )

    def test_both_branches_add_entries_merge_clean(
        self, run_cli, tmp_path: Path,
    ) -> None:
        """Two branches each add an entry. Driver merges cleanly."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_test_repo(run_cli, repo)
        _configure_merge_driver(repo)

        run_sync_ok(run_cli, repo, "sync", "export")
        _add_and_commit(repo, "baseline")

        _git(repo, "checkout", "-b", "branch-a")
        run_ok(
            run_cli, repo,
            "add", "--title", "Entry A", "--type", "note",
            "Body from branch A",
        )
        run_sync_ok(run_cli, repo, "sync", "export")
        _add_and_commit(repo, "branch-a entry")

        _git(repo, "checkout", "master")
        run_ok(
            run_cli, repo,
            "add", "--title", "Entry B", "--type", "decision",
            "Body from master",
        )
        run_sync_ok(run_cli, repo, "sync", "export")
        _add_and_commit(repo, "master entry")

        result = _git(
            repo, "merge", "branch-a", "-m", "merge",
            check=False,
        )
        assert result.returncode == 0, (
            f"Merge failed!\nSTDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

        _assert_no_conflict_markers(repo)

        entries = _read_jsonl(
            repo / "memory" / "entries" / "entries.jsonl"
        )
        titles = {e.get("title", "") for e in entries}
        assert "Entry A" in titles, f"Entry A missing. Titles: {titles}"
        assert "Entry B" in titles, f"Entry B missing. Titles: {titles}"

    def test_public_id_collision_resequenced(
        self, run_cli, tmp_path: Path,
    ) -> None:
        """Both branches increment the same counter. Driver resequences."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_test_repo(run_cli, repo)
        _configure_merge_driver(repo)

        run_ok(
            run_cli, repo,
            "add", "--title", "Seed", "--type", "note", "Seed body",
        )
        run_sync_ok(run_cli, repo, "sync", "export")
        _add_and_commit(repo, "baseline")

        _git(repo, "checkout", "-b", "branch-a")
        run_ok(
            run_cli, repo,
            "add", "--title", "Branch A entry", "--type", "note",
            "A body",
        )
        run_sync_ok(run_cli, repo, "sync", "export")
        _add_and_commit(repo, "branch-a entry")

        _git(repo, "checkout", "master")
        run_ok(
            run_cli, repo,
            "add", "--title", "Master entry", "--type", "note",
            "Master body",
        )
        run_sync_ok(run_cli, repo, "sync", "export")
        _add_and_commit(repo, "master entry")

        result = _git(
            repo, "merge", "branch-a", "-m", "merge",
            check=False,
        )
        assert result.returncode == 0, (
            f"Merge failed!\nSTDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

        entries = _read_jsonl(
            repo / "memory" / "entries" / "entries.jsonl"
        )
        public_ids = [r["public_id"] for r in entries]
        assert len(public_ids) == len(set(public_ids)), (
            f"Duplicate public_ids after merge: {public_ids}"
        )

        titles = {e["title"] for e in entries}
        assert "Seed" in titles
        assert "Branch A entry" in titles
        assert "Master entry" in titles

    def test_merge_resolve_fallback(
        self, run_cli, tmp_path: Path,
    ) -> None:
        """Without the driver, conflicts appear. merge-resolve fixes them."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_test_repo(run_cli, repo)
        _unconfigure_merge_driver(repo)

        run_ok(
            run_cli, repo,
            "add", "--title", "Seed", "--type", "note", "Seed body",
        )
        run_sync_ok(run_cli, repo, "sync", "export")
        _add_and_commit(repo, "baseline")

        _git(repo, "checkout", "-b", "branch-a")
        run_ok(
            run_cli, repo,
            "add", "--title", "A entry", "--type", "note", "A body",
        )
        run_sync_ok(run_cli, repo, "sync", "export")
        _add_and_commit(repo, "branch-a")

        _git(repo, "checkout", "master")
        run_ok(
            run_cli, repo,
            "add", "--title", "Master entry", "--type", "note",
            "M body",
        )
        run_sync_ok(run_cli, repo, "sync", "export")
        _add_and_commit(repo, "master")

        merge_result = _git(
            repo, "merge", "branch-a", "-m", "merge", check=False,
        )

        if merge_result.returncode == 0:
            pytest.skip("Git resolved without conflicts")

        has_conflicts = any(
            "<<<<<<<" in f.read_text(encoding="utf-8")
            for f in (repo / "memory").rglob("*.jsonl")
        )
        if not has_conflicts:
            pytest.skip("No JSONL conflicts to test fallback on")

        completed = run_cli(repo, "merge-resolve")
        assert completed.returncode == 0, (
            f"merge-resolve failed!\n"
            f"STDOUT:\n{completed.stdout}\n"
            f"STDERR:\n{completed.stderr}"
        )

        _assert_no_conflict_markers(repo)

    def test_init_configures_merge_driver(
        self, run_cli, tmp_path: Path,
    ) -> None:
        """cwmem init sets up .gitattributes and .git/config."""
        repo = tmp_path / "repo"
        repo.mkdir()

        _git(repo, "init")
        _git(repo, "config", "user.email", "test@test.com")
        _git(repo, "config", "user.name", "Test")
        init_repo(run_cli, repo)

        ga = repo / ".gitattributes"
        assert ga.is_file(), ".gitattributes should exist"
        content = ga.read_text(encoding="utf-8")
        assert "merge=cwmem-jsonl" in content

        config_result = _git(
            repo, "config", "--local", "merge.cwmem-jsonl.driver",
        )
        assert config_result.returncode == 0
        assert "merge-driver" in config_result.stdout
