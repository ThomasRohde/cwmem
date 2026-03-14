from __future__ import annotations

import sys

import click
import typer
from typer.main import get_command

from cwmem.cli import graph, maintenance, read, setup, sync, write
from cwmem.output.envelope import (
    emit_internal_failure,
    run_cli_command,
    validation_error,
)

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Repo-native institutional memory CLI.",
    no_args_is_help=False,
)

setup.register(app)
read.register(app)
write.register(app)
graph.register(app)
sync.register(app)
maintenance.register(app)


def main() -> None:
    """Run the CLI with envelope-safe error handling."""
    try:
        if _maybe_render_human_help():
            raise SystemExit(0)
        app(standalone_mode=False)
    except click.exceptions.ClickException as exc:
        message = exc.format_message()
        exception_type = type(exc).__name__
        exit_code = run_cli_command(
            "system.cli",
            "repository",
            lambda: (_ for _ in ()).throw(
                validation_error(
                    message,
                    details={"exception_type": exception_type},
                )
            ),
        )
        raise SystemExit(exit_code) from exc
    except click.exceptions.Exit as exc:
        raise SystemExit(exc.exit_code) from exc
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - defensive fallback
        emit_internal_failure(exc, command="system.cli")
        raise SystemExit(90) from exc


def _maybe_render_human_help() -> bool:
    if len(sys.argv) == 1:
        return _render_top_level_help()
    if len(sys.argv) == 2 and sys.argv[1] in {"-h", "--help"}:
        return _render_top_level_help()
    return False


def _render_top_level_help() -> bool:
    command = get_command(app)
    if not isinstance(command, click.Group):  # pragma: no cover - defensive guard
        raise RuntimeError("cwmem top-level app must be a Click group")
    command_width = max(len(name) for name in command.commands)
    lines = [
        "Usage: cwmem [OPTIONS] COMMAND [ARGS]...",
        "",
        "  Repo-native institutional memory CLI.",
        "",
        "Options:",
        "  -h, --help  Show this message and exit.",
        "",
        "Commands:",
    ]
    for name, subcommand in command.commands.items():
        summary = subcommand.get_short_help_str().strip()
        if summary:
            lines.append(f"  {name.ljust(command_width)}  {summary}")
        else:
            lines.append(f"  {name}")
    click.echo("\n".join(lines), color=False)
    return True


if __name__ == "__main__":
    main()

