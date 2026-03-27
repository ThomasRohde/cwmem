"""CLI commands for JSONL merge conflict resolution.

``cwmem merge-driver``  — git merge driver protocol (invoked by git)
``cwmem merge``         — manual fallback for existing conflict markers
"""

from __future__ import annotations

# ruff: noqa: B008
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer

from cwmem.core.merge import (
    MergeError,
    resolve_conflicted_jsonl,
    run_merge_driver,
    serialize_jsonl,
)
from cwmem.output.envelope import run_cli_command


def merge_driver_command(
    base: Path = typer.Argument(..., help="Common ancestor (%O)"),
    ours: Path = typer.Argument(..., help="Current branch (%A) — output target"),
    theirs: Path = typer.Argument(..., help="Other branch (%B)"),
    marker_size: int = typer.Argument(7, help="Conflict marker size (%L)"),
    file_path: str = typer.Argument(..., help="Original file path (%P)"),
) -> None:
    """Git merge driver for JSONL files. Invoked by git, not by users."""
    _ = marker_size  # Required by protocol but unused
    raise SystemExit(run_merge_driver(base, ours, theirs, file_path))


def merge_command(  # noqa: B008
    dry_run: bool = typer.Option(False, "--dry-run"),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    """Resolve JSONL merge conflicts from existing conflict markers."""
    root = (cwd or Path.cwd()).resolve()

    def handler() -> object:
        return _resolve_conflicts(root, dry_run=dry_run)

    raise SystemExit(run_cli_command("memory.merge", "repository", handler))


def _resolve_conflicts(root: Path, *, dry_run: bool) -> dict[str, Any]:
    memory_dir = root / "memory"
    jsonl_files = sorted(memory_dir.rglob("*.jsonl")) if memory_dir.is_dir() else []

    conflicted: list[Path] = []
    for path in jsonl_files:
        content = path.read_text(encoding="utf-8")
        if "<<<<<<<" in content:
            conflicted.append(path)

    if not conflicted:
        return {
            "files_resolved": [],
            "records_merged": 0,
            "public_ids_resequenced": [],
            "dry_run": dry_run,
        }

    files_resolved: list[str] = []
    total_merged = 0
    all_resequenced: list[list[str]] = []

    for path in conflicted:
        content = path.read_text(encoding="utf-8")
        relative = path.relative_to(root).as_posix()

        try:
            result = resolve_conflicted_jsonl(content, relative)
        except MergeError:
            print(f"cwmem merge: failed to parse {relative}", file=sys.stderr)
            continue

        if result.conflicts:
            # Unresolvable — report but continue with other files
            print(
                f"cwmem merge: unresolvable conflicts in {relative} "
                f"({len(result.conflicts)} conflicts)",
                file=sys.stderr,
            )
            continue

        if not dry_run:
            output = serialize_jsonl(result.records)
            path.write_bytes(output)

        files_resolved.append(relative)
        total_merged += result.records_from_ours + result.records_from_theirs
        for old_id, new_id in result.public_ids_resequenced:
            all_resequenced.append([old_id, new_id])

    # Stage resolved files and reconcile (unless dry-run)
    if not dry_run and files_resolved:
        for rel in files_resolved:
            subprocess.run(
                ["git", "add", rel],
                cwd=root,
                check=False,
                capture_output=True,
            )

    return {
        "files_resolved": files_resolved,
        "records_merged": total_merged,
        "public_ids_resequenced": all_resequenced,
        "dry_run": dry_run,
    }


def register(app: typer.Typer) -> None:
    merge_app = typer.Typer(help="JSONL merge conflict resolution.")
    merge_app.command("driver")(merge_driver_command)
    app.add_typer(merge_app, name="merge")
    app.command("merge-driver", hidden=True)(merge_driver_command)
    app.command("merge-resolve", hidden=True)(merge_command)
