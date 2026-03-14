from __future__ import annotations

import typer

from cwmem.cli.setup import placeholder_command
from cwmem.output.envelope import run_cli_command

PLACEHOLDER_CONTEXT = {"allow_extra_args": True, "ignore_unknown_options": True}


def register(app: typer.Typer) -> None:
    sync_app = typer.Typer(help="Synchronization workflows.")

    @sync_app.command("export", context_settings=PLACEHOLDER_CONTEXT)
    def export_command(ctx: typer.Context) -> None:
        _ = ctx.args
        raise SystemExit(
            run_cli_command(
                "memory.sync.export",
                "repository",
                lambda: placeholder_command("memory.sync.export", "sync export"),
            )
        )

    @sync_app.command("import", context_settings=PLACEHOLDER_CONTEXT)
    def import_command(ctx: typer.Context) -> None:
        _ = ctx.args
        raise SystemExit(
            run_cli_command(
                "memory.sync.import",
                "repository",
                lambda: placeholder_command("memory.sync.import", "sync import"),
            )
        )

    app.add_typer(sync_app, name="sync")

