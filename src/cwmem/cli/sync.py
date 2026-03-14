from __future__ import annotations

# ruff: noqa: B008
from pathlib import Path
from typing import Any

import typer

from cwmem.core import planner as _planner
from cwmem.core.export import export_snapshot
from cwmem.core.importer import import_snapshot
from cwmem.core.safety import execute_mutation
from cwmem.output.envelope import run_cli_command


def export_command(  # noqa: B008
    dry_run: bool = typer.Option(False, "--dry-run"),
    check: bool = typer.Option(False, "--check"),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    plan_out: Path | None = typer.Option(None, "--plan-out"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    wait_lock: float = typer.Option(0.0, "--wait-lock", min=0.0),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()
    target_dir = (output_dir if output_dir is not None else (root / "memory")).resolve()
    plan_path = _planned_path(root, "sync.export", plan_out, enable_default=not check)

    def handler() -> object:
        if check and not dry_run and plan_path is None and idempotency_key is None:
            return export_snapshot(root, target_dir, check=True).model_dump(mode="json")

        return execute_mutation(
            root=root,
            command_id="memory.sync.export",
            request_payload={
                "command": "memory.sync.export",
                "check": check,
                "output_dir": target_dir.as_posix(),
                "request_hash": _planner.export_request_hash(
                    root, output_dir=target_dir, check=check
                ),
            },
            apply_handler=lambda apply_root: _export_result(
                apply_root,
                target_dir=target_dir,
                check=check,
                plan_path=plan_path,
            ),
            preview_handler=lambda: _export_preview(
                root,
                target_dir=target_dir,
                check=check,
                plan_path=plan_path,
            ),
            summary_builder=lambda result: {
                "files": len(result.get("files", [])),
                "drift": len(result.get("drift", [])),
            },
            dry_run=dry_run,
            idempotency_key=idempotency_key,
            wait_lock=wait_lock,
        )

    raise SystemExit(run_cli_command("memory.sync.export", "repository", handler))


def import_command(  # noqa: B008
    dry_run: bool = typer.Option(False, "--dry-run"),
    fail_on_drift: bool = typer.Option(False, "--fail-on-drift"),
    input_dir: Path | None = typer.Option(None, "--input-dir"),
    plan_out: Path | None = typer.Option(None, "--plan-out"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    wait_lock: float = typer.Option(0.0, "--wait-lock", min=0.0),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()
    source_dir = (input_dir if input_dir is not None else (root / "memory")).resolve()
    plan_path = _planned_path(root, "sync.import", plan_out, enable_default=True)

    def handler() -> object:
        return execute_mutation(
            root=root,
            command_id="memory.sync.import",
            request_payload={
                "command": "memory.sync.import",
                "input_dir": source_dir.as_posix(),
                "fail_on_drift": fail_on_drift,
                "request_hash": _planner.import_request_hash(
                    root,
                    input_dir=source_dir,
                    fail_on_drift=fail_on_drift,
                ),
            },
            apply_handler=lambda apply_root: _import_result(
                apply_root,
                source_dir=source_dir,
                fail_on_drift=fail_on_drift,
                plan_path=plan_path,
            ),
            preview_handler=lambda: _import_preview(
                root,
                source_dir=source_dir,
                fail_on_drift=fail_on_drift,
                plan_path=plan_path,
            ),
            summary_builder=lambda result: dict(result.get("plan", {}).get("summary", {})),
            dry_run=dry_run,
            idempotency_key=idempotency_key,
            wait_lock=wait_lock,
        )

    raise SystemExit(run_cli_command("memory.sync.import", "repository", handler))


def register(app: typer.Typer) -> None:
    sync_app = typer.Typer(help="Synchronization workflows.")
    sync_app.command("export")(export_command)
    sync_app.command("import")(import_command)
    app.add_typer(sync_app, name="sync")


def _planned_path(
    root: Path, workflow: str, plan_out: Path | None, *, enable_default: bool
) -> Path | None:
    if plan_out is not None:
        return plan_out.resolve()
    if enable_default:
        return _planner.default_plan_path(root, workflow)
    return None


def _export_preview(
    root: Path, *, target_dir: Path, check: bool, plan_path: Path | None
) -> dict[str, Any]:
    artifact = _planner.plan_sync_export(
        root,
        output_dir=target_dir,
        check=check,
        plan_out=plan_path,
    )
    return {
        **artifact.payload,
        "plan_artifact": artifact.plan_path,
        "plan": artifact.model_dump(mode="json"),
    }


def _export_result(
    root: Path, *, target_dir: Path, check: bool, plan_path: Path | None
) -> dict[str, Any]:
    result = export_snapshot(root, target_dir, check=check).model_dump(mode="json")
    if plan_path is not None:
        artifact = _planner.plan_sync_export(
            root,
            output_dir=target_dir,
            check=check,
            plan_out=plan_path,
        )
        result["plan_artifact"] = artifact.plan_path
        result["plan"] = artifact.model_dump(mode="json")
    return result


def _import_preview(
    root: Path,
    *,
    source_dir: Path,
    fail_on_drift: bool,
    plan_path: Path | None,
) -> dict[str, Any]:
    _fail_on_export_drift(root, fail_on_drift=fail_on_drift)
    artifact = _planner.plan_sync_import(
        root,
        input_dir=source_dir,
        fail_on_drift=fail_on_drift,
        plan_out=plan_path,
    )
    result = import_snapshot(root, source_dir, dry_run=True).model_dump(mode="json")
    result["plan_artifact"] = artifact.plan_path
    result["workflow_plan"] = artifact.model_dump(mode="json")
    return result


def _import_result(
    root: Path,
    *,
    source_dir: Path,
    fail_on_drift: bool,
    plan_path: Path | None,
) -> dict[str, Any]:
    _fail_on_export_drift(root, fail_on_drift=fail_on_drift)
    if plan_path is not None:
        artifact = _planner.plan_sync_import(
            root,
            input_dir=source_dir,
            fail_on_drift=fail_on_drift,
            plan_out=plan_path,
        )
    else:
        artifact = None
    result = import_snapshot(root, source_dir, dry_run=False).model_dump(mode="json")
    if artifact is not None:
        result["plan_artifact"] = artifact.plan_path
        result["workflow_plan"] = artifact.model_dump(mode="json")
    return result


def _fail_on_export_drift(root: Path, *, fail_on_drift: bool) -> None:
    if not fail_on_drift:
        return
    manifest_path = root / "memory" / "manifests" / "export-manifest.json"
    if not manifest_path.is_file():
        return
    export_snapshot(root, root / "memory", check=True)
