from __future__ import annotations

import click
import typer

from cwmem.cli import graph, maintenance, read, setup, sync, write
from cwmem.output.envelope import (
    emit_internal_failure,
    run_cli_command,
    validation_error,
)

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": []},
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


if __name__ == "__main__":
    main()

