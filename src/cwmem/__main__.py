from __future__ import annotations

import sys

import click
import typer
from typer.main import get_command

from cwmem import __version__
from cwmem.cli import graph, maintenance, read, setup, sync, write
from cwmem.output.envelope import (
    emit_internal_failure,
    run_cli_command,
    validation_error,
)

TOP_LEVEL_HELP = """cwmem stores repository-scoped memory next to your codebase so teams can
capture decisions, events, entities, and relationships in a searchable,
syncable format.

Typical flow:
  1. Run `cwmem init` to create the runtime database and tracked memory files.
  2. Capture context with `cwmem add`, `cwmem event-add`, or `cwmem link`.
  3. Retrieve it later with `cwmem search`, `cwmem related`, or `cwmem get`.
  4. Keep checked-in artifacts aligned with `cwmem sync export` / `sync import`.

For machine-readable schemas, workflows, and error contracts, run `cwmem guide`."""

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help=TOP_LEVEL_HELP,
    no_args_is_help=True,
)

setup.register(app)
read.register(app)
write.register(app)
graph.register(app)
sync.register(app)
maintenance.register(app)


def main() -> None:
    """Run the CLI with envelope-safe error handling."""
    command = _build_click_app()
    try:
        command.main(args=sys.argv[1:], prog_name="cwmem", standalone_mode=False)
    except click.exceptions.NoArgsIsHelpError as exc:
        raise SystemExit(0) from exc
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


def _build_click_app() -> click.Command:
    command = get_command(app)
    if not isinstance(command, click.Group):  # pragma: no cover - defensive guard
        raise RuntimeError("cwmem top-level app must be a Click group")
    command.help = TOP_LEVEL_HELP
    command.params.insert(
        0,
        click.Option(
            ["-V", "--version"],
            is_flag=True,
            is_eager=True,
            expose_value=False,
            callback=_show_version,
            help="Show package version and exit.",
        ),
    )
    guide = setup.build_guide_document()
    summaries = {
        item["name"]: _command_summary_from_catalog(item)
        for item in guide.command_catalog
        if " " not in item["name"]
    }
    summaries["sync"] = "Export or import checked-in collaboration artifacts."
    for name, subcommand in command.commands.items():
        summary = summaries.get(name)
        if summary:
            subcommand.help = summary
            subcommand.short_help = summary
    return command


def _command_summary_from_catalog(item: dict[str, object]) -> str:
    summary = str(item["summary"])
    if not bool(item["implemented"]):
        return f"{summary} [not yet implemented]"
    return summary


def _show_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    _ = param
    if not value or ctx.resilient_parsing:
        return
    click.echo(__version__)
    ctx.exit()


if __name__ == "__main__":
    main()

