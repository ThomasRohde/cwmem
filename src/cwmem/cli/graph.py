from __future__ import annotations

import typer

from cwmem.cli.setup import placeholder_command
from cwmem.output.envelope import run_cli_command

PLACEHOLDER_CONTEXT = {"allow_extra_args": True, "ignore_unknown_options": True}


def register(app: typer.Typer) -> None:
    @app.command("graph", context_settings=PLACEHOLDER_CONTEXT)
    def graph_command(ctx: typer.Context) -> None:
        _ = ctx.args
        raise SystemExit(
            run_cli_command(
                "memory.graph.show",
                "graph",
                lambda: placeholder_command("memory.graph.show", "graph"),
            )
        )

