from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from cwmem.cli.setup import placeholder_command
from cwmem.core.store import get_stats, rebuild_index, validate_index
from cwmem.output.envelope import run_cli_command

PLACEHOLDER_CONTEXT = {"allow_extra_args": True, "ignore_unknown_options": True}


def build_command(  # noqa: B008
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        entry_count, event_count = rebuild_index(root)
        stats = get_stats(root)
        return {
            'rebuilt': True,
            'entries_indexed': entry_count,
            'events_indexed': event_count,
            'stats': stats,
        }

    raise SystemExit(run_cli_command('system.build', 'repository', handler))


def stats_command(  # noqa: B008
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        stats = get_stats(root)
        return {'stats': stats}

    raise SystemExit(run_cli_command('system.stats', 'repository', handler))


def validate_command(  # noqa: B008
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        result = validate_index(root)
        return {
            'ok': result.ok,
            'issues': result.issues,
            'issue_count': len(result.issues),
        }

    raise SystemExit(run_cli_command('system.validate', 'repository', handler))


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

