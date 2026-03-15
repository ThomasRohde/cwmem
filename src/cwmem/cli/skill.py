from __future__ import annotations

# ruff: noqa: B008
from pathlib import Path

import typer

from cwmem.core.safety import execute_mutation
from cwmem.core.skills import install_skill
from cwmem.core.store import ensure_schema
from cwmem.output.envelope import run_cli_command


def skill_command(  # noqa: B008
    target: str = typer.Option(
        "auto",
        "--target",
        help="Install target selection: auto, copilot, claude, or agents.",
    ),
    strategy: str = typer.Option(
        "copy",
        "--strategy",
        help="Materialization strategy: copy files or create a link.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite conflicting installed skill files.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview the install without writing files.",
    ),
    idempotency_key: str | None = typer.Option(
        None,
        "--idempotency-key",
        help="Replay-safe key for retried installs.",
    ),
    wait_lock: float = typer.Option(
        0.0,
        "--wait-lock",
        min=0.0,
        help="Seconds to wait for the repository write lock.",
    ),
    cwd: Path | None = typer.Option(
        None,
        "--cwd",
        help="Repository root to inspect and update.",
    ),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> object:
        if idempotency_key is not None and not dry_run:
            ensure_schema(root)
        return execute_mutation(
            root=root,
            command_id="system.skill.install",
            request_payload={
                "command": "system.skill.install",
                "target": target,
                "strategy": strategy,
                "force": force,
                "root": root.as_posix(),
            },
            apply_handler=lambda _apply_root: install_skill(
                root,
                requested_target=target,
                strategy=strategy,
                force=force,
                apply=True,
            ).model_dump(mode="json"),
            preview_handler=lambda: install_skill(
                root,
                requested_target=target,
                strategy=strategy,
                force=force,
                apply=False,
            ).model_dump(mode="json"),
            summary_builder=lambda result: {
                "targets": len(result.get("resolved_targets", [])),
                "written_files": len(result.get("written_files", [])),
                "recommendations": len(result.get("recommendations", [])),
            },
            dry_run=dry_run,
            idempotency_key=idempotency_key,
            wait_lock=wait_lock,
        )

    raise SystemExit(run_cli_command("system.skill.install", "repository", handler))


def register(app: typer.Typer) -> None:
    app.command("skill")(skill_command)
