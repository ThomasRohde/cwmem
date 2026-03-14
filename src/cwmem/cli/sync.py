from __future__ import annotations

# ruff: noqa: B008
from pathlib import Path

import typer

from cwmem.core.export import export_snapshot
from cwmem.core.importer import import_snapshot
from cwmem.output.envelope import run_cli_command


def export_command(  # noqa: B008
    check: bool = typer.Option(False, "--check"),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()
    target_dir = (output_dir if output_dir is not None else (root / "memory")).resolve()

    def handler() -> object:
        return export_snapshot(root, target_dir, check=check)

    raise SystemExit(run_cli_command("memory.sync.export", "repository", handler))


def import_command(  # noqa: B008
    dry_run: bool = typer.Option(False, "--dry-run"),
    input_dir: Path | None = typer.Option(None, "--input-dir"),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()
    source_dir = (input_dir if input_dir is not None else (root / "memory")).resolve()

    def handler() -> object:
        return import_snapshot(root, source_dir, dry_run=dry_run)

    raise SystemExit(run_cli_command("memory.sync.import", "repository", handler))


def register(app: typer.Typer) -> None:
    sync_app = typer.Typer(help="Synchronization workflows.")
    sync_app.command("export")(export_command)
    sync_app.command("import")(import_command)
    app.add_typer(sync_app, name="sync")
