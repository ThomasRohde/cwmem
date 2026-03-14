from __future__ import annotations

import os
import sys
from pathlib import Path

import typer

from cwmem.output.envelope import run_cli_command, validation_error


def _launch_error(message: str, *, details: dict[str, object] | None = None) -> int:
    return run_cli_command(
        "system.tui",
        "repository",
        lambda: (_ for _ in ()).throw(validation_error(message, details=details or {})),
    )


def _require_interactive_terminal() -> None:
    stdin_isatty = sys.stdin.isatty()
    stdout_isatty = sys.stdout.isatty()
    if not stdin_isatty or not stdout_isatty:
        details: dict[str, object] = {
            "stdin_isatty": stdin_isatty,
            "stdout_isatty": stdout_isatty,
        }
        if os.environ.get("LLM", "").lower() == "true":
            details["environment_variable"] = "LLM"
            details["value"] = "true"
        raise SystemExit(
            _launch_error(
                "`cwmem tui` requires an interactive TTY on stdin and stdout.",
                details=details,
            )
        )


def tui_command(  # noqa: B008
    cwd: Path | None = typer.Option(None, "--cwd"),  # noqa: B008
) -> None:
    _require_interactive_terminal()
    root = (cwd or Path.cwd()).resolve()

    try:
        from cwmem.tui.app import CwmemTuiApp
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("textual"):
            raise SystemExit(
                _launch_error(
                    "The Textual dependency is unavailable, so `cwmem tui` cannot start.",
                    details={"missing_module": exc.name},
                )
            ) from exc
        raise

    CwmemTuiApp(root=root).run()


def register(app: typer.Typer) -> None:
    app.command("tui")(tui_command)
