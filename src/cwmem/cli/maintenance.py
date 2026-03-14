from __future__ import annotations

# ruff: noqa: B008
from pathlib import Path
from typing import Any

import typer

from cwmem.cli.setup import placeholder_command
from cwmem.core.store import get_fts_stats, rebuild_fts_index, validate_fts
from cwmem.output.envelope import run_cli_command

PLACEHOLDER_CONTEXT = {"allow_extra_args": True, "ignore_unknown_options": True}


def build_command(
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        entry_count, event_count, embedding_count = rebuild_fts_index(root)
        return {
            "entries_indexed": entry_count,
            "events_indexed": event_count,
            "embeddings_written": embedding_count,
        }

    raise SystemExit(run_cli_command("system.build", "repository", handler))


def stats_command(
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        result = get_fts_stats(root)
        return result.model_dump()

    raise SystemExit(run_cli_command("system.stats", "repository", handler))


def validate_command(
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        result = validate_fts(root)
        return result.model_dump()

    raise SystemExit(run_cli_command("system.validate", "repository", handler))


def _make_placeholder(command_id: str, human_name: str):
    def command(ctx: typer.Context) -> None:
        _ = ctx.args
        raise SystemExit(
            run_cli_command(
                command_id,
                "repository",
                lambda: placeholder_command(command_id, human_name),
            )
        )

    return command


def register(app: typer.Typer) -> None:
    app.command("build")(build_command)
    app.command("stats")(stats_command)
    app.command("validate")(validate_command)
    app.command("plan", context_settings=PLACEHOLDER_CONTEXT)(
        _make_placeholder("system.plan", "plan")
    )
    app.command("apply", context_settings=PLACEHOLDER_CONTEXT)(
        _make_placeholder("system.apply", "apply")
    )
    app.command("verify", context_settings=PLACEHOLDER_CONTEXT)(
        _make_placeholder("system.verify", "verify")
    )
