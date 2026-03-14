from __future__ import annotations

# ruff: noqa: B008
from pathlib import Path
from typing import Any, NoReturn

import typer

from cwmem.core import planner as _planner
from cwmem.core import validator as _validator
from cwmem.core.models import PlanArtifact, ValidationIssue
from cwmem.core.safety import execute_mutation
from cwmem.core.store import get_fts_stats, rebuild_fts_index
from cwmem.output.envelope import (
    conflict_error,
    io_read_error,
    run_cli_command,
    validation_error,
)

PLAN_WORKFLOW_ALIASES = {
    "sync-export": "sync-export",
    "export": "sync-export",
    "sync-import": "sync-import",
    "import": "sync-import",
}
SUPPORTED_PLAN_WORKFLOWS = tuple(sorted({value for value in PLAN_WORKFLOW_ALIASES.values()}))
CONCEPTUAL_GUIDE_WORKFLOWS = ("bootstrap", "safe-mutation", "explicit-sync")


def build_command(
    dry_run: bool = typer.Option(False, "--dry-run"),
    wait_lock: float = typer.Option(0.0, "--wait-lock", min=0.0),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        return execute_mutation(
            root=root,
            command_id="system.build",
            request_payload={
                "command": "system.build",
                "stats": get_fts_stats(root).model_dump(mode="json"),
            },
            apply_handler=lambda apply_root: _build_result(apply_root),
            preview_handler=lambda: _build_preview(root),
            summary_builder=lambda result: {
                "entries_to_index": int(result.get("entries_indexed", 0)),
                "events_to_index": int(result.get("events_indexed", 0)),
                "embeddings_to_refresh": int(result.get("embeddings_written", 0)),
            },
            dry_run=dry_run,
            wait_lock=wait_lock,
        )

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
    plan_file: Path | None = typer.Option(None, "--plan"),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        if plan_file is not None:
            try:
                result = _planner.validate_plan(root, plan_file.resolve())
            except _planner.PlanArtifactError as exc:
                _raise_plan_artifact_error(exc)
        else:
            result = _validator.validate_repository(root)
        if not result.ok:
            raise validation_error(
                "Repository validation found issues.",
                details=result.model_dump(mode="json"),
            )
        return result.model_dump(mode="json")

    raise SystemExit(run_cli_command("system.validate", "repository", handler))


def plan_command(
    workflow: str = typer.Argument(
        ...,
        metavar="WORKFLOW",
        help=(
            "Valid values: sync-export or sync-import. Conceptual guide workflows such as "
            "bootstrap are sequences, not direct `plan` arguments."
        ),
    ),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    input_dir: Path | None = typer.Option(None, "--input-dir"),
    check: bool = typer.Option(False, "--check"),
    fail_on_drift: bool = typer.Option(False, "--fail-on-drift"),
    plan_out: Path | None = typer.Option(None, "--plan-out"),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()
    normalized_workflow = _normalize_workflow_name(workflow)

    def handler() -> dict[str, Any]:
        if normalized_workflow == "sync-export":
            artifact = _planner.plan_sync_export(
                root,
                output_dir=output_dir,
                check=check,
                plan_out=plan_out.resolve() if plan_out is not None else None,
            )
        elif normalized_workflow == "sync-import":
            artifact = _planner.plan_sync_import(
                root,
                input_dir=input_dir,
                fail_on_drift=fail_on_drift,
                plan_out=plan_out.resolve() if plan_out is not None else None,
            )
        else:
            raise validation_error(
                (
                    "Unsupported workflow. Use `sync-export` or `sync-import`. "
                    "Conceptual guide workflows such as `bootstrap`, `safe-mutation`, and "
                    "`explicit-sync` describe sequences and are not direct `plan` arguments."
                ),
                details={
                    "workflow": workflow,
                    "normalized_workflow": normalized_workflow,
                    "supported_workflows": list(SUPPORTED_PLAN_WORKFLOWS),
                    "conceptual_workflows": list(CONCEPTUAL_GUIDE_WORKFLOWS),
                },
            )
        return artifact.model_dump(mode="json")

    raise SystemExit(run_cli_command("system.plan", "repository", handler))


def apply_command(
    plan_file: Path = typer.Option(..., "--plan"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    wait_lock: float = typer.Option(0.0, "--wait-lock", min=0.0),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()
    plan_path = plan_file.resolve()

    def handler() -> dict[str, Any]:
        try:
            artifact = _planner.load_plan_artifact(plan_path)
        except _planner.PlanArtifactError as exc:
            _raise_plan_artifact_error(exc)

        validation = _planner.validate_loaded_plan(root, artifact)
        if not validation.ok:
            raise conflict_error(
                "The saved plan no longer matches the current repository state.",
                details={
                    "plan": plan_path.as_posix(),
                    "issues": [issue.model_dump(mode="json") for issue in validation.issues],
                },
            )

        return execute_mutation(
            root=root,
            command_id="system.apply",
            request_payload={
                "command": "system.apply",
                "workflow": artifact.workflow,
                "plan": artifact.request_hash,
                "idempotency_key": idempotency_key,
            },
            apply_handler=lambda apply_root: _apply_plan_result(
                apply_root,
                artifact=artifact,
            ),
            preview_handler=lambda: _apply_plan_preview(artifact),
            summary_builder=lambda _result: dict(artifact.summary),
            dry_run=dry_run,
            idempotency_key=idempotency_key,
            wait_lock=wait_lock,
        )

    raise SystemExit(run_cli_command("system.apply", "repository", handler))


def verify_command(
    plan_file: Path | None = typer.Option(None, "--plan"),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        result = _validator.verify_repository(
            root,
            plan_path=plan_file.resolve() if plan_file is not None else None,
        )
        if not result.ok:
            raise validation_error(
                "Repository verification failed.",
                details=result.model_dump(mode="json"),
            )
        return result.model_dump(mode="json")

    raise SystemExit(run_cli_command("system.verify", "repository", handler))


def register(app: typer.Typer) -> None:
    app.command("build")(build_command)
    app.command("stats")(stats_command)
    app.command("validate")(validate_command)
    app.command("plan")(plan_command)
    app.command("apply")(apply_command)
    app.command("verify")(verify_command)


def _raise_plan_artifact_error(exc: _planner.PlanArtifactError) -> NoReturn:
    details = dict(exc.details)
    details["plan_error_kind"] = exc.error_kind
    if exc.error_kind in {"missing", "read"}:
        raise io_read_error(str(exc), details=details)
    raise validation_error(str(exc), details=details)


def _build_preview(root: Path) -> dict[str, Any]:
    stats = get_fts_stats(root)
    return {
        "entries_indexed": stats.entries,
        "events_indexed": stats.events,
        "embeddings_written": stats.entries + stats.events,
    }


def _build_result(root: Path) -> dict[str, Any]:
    entry_count, event_count, embedding_count = rebuild_fts_index(root)
    return {
        "entries_indexed": entry_count,
        "events_indexed": event_count,
        "embeddings_written": embedding_count,
    }


def _apply_plan_preview(artifact: PlanArtifact) -> dict[str, Any]:
    payload = dict(artifact.payload)
    payload["plan_artifact"] = artifact.plan_path
    payload["workflow_plan"] = artifact.model_dump(mode="json")
    return payload


def _apply_plan_result(root: Path, *, artifact: PlanArtifact) -> dict[str, Any]:
    if artifact.workflow == "sync.export":
        target_dir = Path(str(artifact.options["output_dir"]))
        result = _export_apply(
            root,
            target_dir=target_dir,
            check=bool(artifact.options.get("check", False)),
        )
    elif artifact.workflow == "sync.import":
        source_dir = Path(str(artifact.options["input_dir"]))
        result = _import_apply(
            root,
            source_dir=source_dir,
            fail_on_drift=bool(artifact.options.get("fail_on_drift", False)),
        )
    else:
        issue = ValidationIssue(
            code="apply.unsupported_workflow",
            message="The saved plan workflow is not supported by apply.",
            details={"workflow": artifact.workflow},
        )
        raise conflict_error(
            issue.message,
            details=issue.model_dump(mode="json"),
        )
    result["plan_artifact"] = artifact.plan_path
    result["workflow_plan"] = artifact.model_dump(mode="json")
    return result


def _export_apply(root: Path, *, target_dir: Path, check: bool) -> dict[str, Any]:
    from cwmem.core.export import export_snapshot

    return export_snapshot(root, target_dir, check=check).model_dump(mode="json")


def _import_apply(root: Path, *, source_dir: Path, fail_on_drift: bool) -> dict[str, Any]:
    from cwmem.cli.sync import _fail_on_export_drift
    from cwmem.core.importer import import_snapshot

    _fail_on_export_drift(root, fail_on_drift=fail_on_drift)
    return import_snapshot(root, source_dir, dry_run=False).model_dump(mode="json")


def _normalize_workflow_name(workflow: str) -> str:
    normalized = workflow.strip().lower().replace("_", "-").replace(".", "-").replace(" ", "-")
    return PLAN_WORKFLOW_ALIASES.get(normalized, normalized)
