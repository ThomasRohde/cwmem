from __future__ import annotations

import sys
from typing import Any, cast

import click
import typer
from typer.main import get_command

from cwmem import __version__
from cwmem.cli import graph, maintenance, read, setup, sync, tui, write
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
  3. Retrieve it later with `cwmem search`, `cwmem related`, `cwmem get`, or `cwmem tui`.
  4. Refresh derived state with `cwmem build`, then keep checked-in artifacts aligned
     with `cwmem sync export` and `cwmem verify`.

For machine-readable schemas, workflows, and error contracts, run `cwmem guide`."""

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help=TOP_LEVEL_HELP,
    no_args_is_help=True,
)

setup.register(app)
tui.register(app)
read.register(app)
write.register(app)
graph.register(app)
sync.register(app)
maintenance.register(app)


def main() -> None:
    """Run the CLI with envelope-safe error handling."""
    command = _build_click_app()
    raw_args = sys.argv[1:]
    try:
        _fail_on_duplicate_scalar_options(command, raw_args)
        command.main(args=raw_args, prog_name="cwmem", standalone_mode=False)
    except click.exceptions.NoArgsIsHelpError as exc:
        try:
            command.main(args=["--help"], prog_name="cwmem", standalone_mode=False)
        except click.exceptions.Exit:
            pass
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
            ["-v", "-V", "--version"],
            is_flag=True,
            is_eager=True,
            expose_value=False,
            callback=_show_version,
            help="Show package version and exit.",
        ),
    )
    guide = setup.build_guide_document()
    command_catalog = {
        str(item["name"]): item for item in guide.command_catalog if " " not in str(item["name"])
    }
    command_catalog["sync"] = {"summary": "Export or import checked-in collaboration artifacts."}
    for name, subcommand in command.commands.items():
        item = command_catalog.get(name)
        if item is None:
            continue
        subcommand.help = _command_help_from_catalog(item)
        subcommand.short_help = _command_summary_from_catalog(item)
        if bool(item.get("hidden", False)):
            subcommand.hidden = True
    _disable_rich_help(command)
    return command


def _command_summary_from_catalog(item: dict[str, object]) -> str:
    summary = str(item["summary"])
    if not bool(item.get("implemented", True)):
        return f"Not yet implemented: {summary}"
    return summary


def _command_help_from_catalog(item: dict[str, object]) -> str:
    help_text = item.get("help")
    if isinstance(help_text, str) and help_text:
        return help_text
    return _command_summary_from_catalog(item)


def _disable_rich_help(command: click.Command) -> None:
    if hasattr(command, "rich_markup_mode"):
        cast(Any, command).rich_markup_mode = None
    if isinstance(command, click.Group):
        for subcommand in command.commands.values():
            _disable_rich_help(subcommand)


def _show_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    _ = param
    if not value or ctx.resilient_parsing:
        return
    click.echo(__version__)
    ctx.exit()


def _fail_on_duplicate_scalar_options(command: click.Command, args: list[str]) -> None:
    leaf_command, option_start_index = _resolve_leaf_command(command, args)
    duplicates = _find_duplicate_scalar_options(leaf_command, args[option_start_index:])
    if not duplicates:
        return
    formatted = ", ".join(f"`{name}`" for name in duplicates)
    raise click.UsageError(
        f"Duplicate scalar options are not allowed: {formatted}. "
        "Provide each option at most once."
    )


def _resolve_leaf_command(command: click.Command, args: list[str]) -> tuple[click.Command, int]:
    current = command
    index = 0
    while isinstance(current, click.Group):
        next_command: click.Command | None = None
        while index < len(args):
            token = args[index]
            if token == "--":
                return current, index + 1
            if not token.startswith("-") and token in current.commands:
                next_command = current.commands[token]
                break
            index += 1
        if next_command is None:
            return current, len(args)
        current = next_command
        index += 1
    return current, index


def _find_duplicate_scalar_options(command: click.Command, args: list[str]) -> list[str]:
    option_lookup: dict[str, click.Option] = {}
    for param in command.params:
        if not isinstance(param, click.Option):
            continue
        for opt in (*param.opts, *param.secondary_opts):
            option_lookup[opt] = param

    duplicates: list[str] = []
    seen: set[int] = set()
    pending_values = 0

    for token in args:
        if pending_values > 0:
            pending_values -= 1
            continue
        if token == "--":
            break

        attached_value = token.startswith("--") and "=" in token
        option_token = token.split("=", 1)[0] if attached_value else token
        option = option_lookup.get(option_token)
        if option is None:
            continue

        if _is_scalar_option(option):
            option_id = id(option)
            canonical_name = _canonical_option_name(option)
            if option_id in seen:
                if canonical_name not in duplicates:
                    duplicates.append(canonical_name)
            else:
                seen.add(option_id)

        if _option_takes_value(option) and not attached_value:
            pending_values = option.nargs

    return duplicates


def _is_scalar_option(option: click.Option) -> bool:
    return not option.multiple and not getattr(option, "count", False) and not option.is_flag


def _option_takes_value(option: click.Option) -> bool:
    return not option.is_flag and option.nargs > 0


def _canonical_option_name(option: click.Option) -> str:
    for opt in option.opts:
        if opt.startswith("--"):
            return opt
    return option.opts[0]


if __name__ == "__main__":
    main()

