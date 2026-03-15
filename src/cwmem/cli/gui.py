from __future__ import annotations

from pathlib import Path

import typer

from cwmem.output.envelope import run_cli_command, validation_error


def _launch_error(message: str, *, details: dict[str, object] | None = None) -> int:
    return run_cli_command(
        "system.gui",
        "repository",
        lambda: (_ for _ in ()).throw(validation_error(message, details=details or {})),
    )


def gui_command(
    cwd: Path | None = typer.Option(None, "--cwd"),  # noqa: B008
    port: int | None = typer.Option(None, "--port", help="HTTP port (0 or omit for auto)"),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open browser automatically"),  # noqa: B008
) -> None:
    root = (cwd or Path.cwd()).resolve()

    try:
        from cwmem.gui.server import run_server
    except ModuleNotFoundError as exc:
        if exc.name and (exc.name.startswith("fastapi") or exc.name.startswith("uvicorn")):
            raise SystemExit(
                _launch_error(
                    "FastAPI or uvicorn dependency is unavailable, so `cwmem gui` cannot start.",
                    details={"missing_module": exc.name},
                )
            ) from exc
        raise

    run_server(root, port=port or 0, no_open=no_open)


def register(app: typer.Typer) -> None:
    app.command("gui")(gui_command)
