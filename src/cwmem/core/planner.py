from __future__ import annotations

from pathlib import Path
from typing import Any

from cwmem.core import export as _export
from cwmem.core import importer as _importer
from cwmem.core import store as _store
from cwmem.core.models import ExportResult, PlanArtifact, ValidationIssue, ValidationResult
from cwmem.core.safety import stable_hash
from cwmem.output.json import to_json_bytes


def default_plan_path(root: Path, workflow: str) -> Path:
    slug = workflow.replace(".", "-").replace("_", "-")
    return root / ".cwmem" / "plans" / f"{slug}-plan.json"


def plan_sync_export(
    root: Path,
    *,
    output_dir: Path | None = None,
    check: bool = False,
    plan_out: Path | None = None,
) -> PlanArtifact:
    components = _sync_export_components(root, output_dir=output_dir, check=check)
    return _write_plan(root, workflow="sync.export", plan_out=plan_out, **components)


def plan_sync_import(
    root: Path,
    *,
    input_dir: Path | None = None,
    fail_on_drift: bool = False,
    plan_out: Path | None = None,
) -> PlanArtifact:
    components = _sync_import_components(
        root,
        input_dir=input_dir,
        fail_on_drift=fail_on_drift,
    )
    return _write_plan(root, workflow="sync.import", plan_out=plan_out, **components)


def load_plan_artifact(path: Path) -> PlanArtifact:
    payload = _store._json_load(path.read_text(encoding="utf-8"))
    return PlanArtifact.model_validate(payload)


def validate_plan(root: Path, plan_path: Path) -> ValidationResult:
    artifact = load_plan_artifact(plan_path.resolve())
    issues: list[ValidationIssue] = []

    if artifact.workflow == "sync.export":
        current = _sync_export_components(
            root,
            output_dir=Path(str(artifact.options["output_dir"])),
            check=bool(artifact.options.get("check", False)),
        )
    elif artifact.workflow == "sync.import":
        current = _sync_import_components(
            root,
            input_dir=Path(str(artifact.options["input_dir"])),
            fail_on_drift=bool(artifact.options.get("fail_on_drift", False)),
        )
    else:
        issues.append(
            ValidationIssue(
                code="plan.unsupported_workflow",
                message="The supplied plan artifact uses an unsupported workflow.",
                details={"workflow": artifact.workflow},
            )
        )
        return ValidationResult(ok=False, issues=issues)

    if artifact.command_id != current["command_id"]:
        issues.append(
            ValidationIssue(
                code="plan.command_mismatch",
                message="The saved plan command does not match the current workflow contract.",
                details={
                    "expected": current["command_id"],
                    "actual": artifact.command_id,
                },
            )
        )

    if artifact.request_hash != current["request_hash"]:
        issues.append(
            ValidationIssue(
                code="plan.state_drift",
                message="The saved plan no longer matches the current repository or source state.",
                details={
                    "expected_request_hash": artifact.request_hash,
                    "actual_request_hash": current["request_hash"],
                },
            )
        )

    return ValidationResult(ok=not issues, issues=issues)


def export_request_hash(root: Path, *, output_dir: Path | None = None, check: bool = False) -> str:
    return _sync_export_components(root, output_dir=output_dir, check=check)["request_hash"]


def import_request_hash(
    root: Path, *, input_dir: Path | None = None, fail_on_drift: bool = False
) -> str:
    source_dir = (input_dir if input_dir is not None else (root / "memory")).resolve()
    snapshot = _importer.load_import_snapshot(source_dir)
    return stable_hash(
        {
            "command_id": "memory.sync.import",
            "input_dir": source_dir.as_posix(),
            "fail_on_drift": fail_on_drift,
            "source_db_fingerprint": snapshot.manifest.source_db_fingerprint,
        }
    )


def _sync_export_components(
    root: Path,
    *,
    output_dir: Path | None = None,
    check: bool = False,
) -> dict[str, Any]:
    target_dir = (output_dir if output_dir is not None else (root / "memory")).resolve()
    bundle = _export.build_export_bundle(root, target_dir)
    drift = _export.compare_export_to_disk(bundle, target_dir)
    payload = ExportResult(
        output_dir=target_dir.as_posix(),
        check=check,
        changed=bool(drift),
        files=bundle.file_records,
        manifest=bundle.manifest,
        drift=drift,
    ).model_dump(mode="json")
    return {
        "command_id": "memory.sync.export",
        "request_hash": stable_hash(
            {
                "command_id": "memory.sync.export",
                "output_dir": target_dir.as_posix(),
                "check": check,
                "source_db_fingerprint": bundle.manifest.source_db_fingerprint,
            }
        ),
        "options": {
            "output_dir": target_dir.as_posix(),
            "check": check,
        },
        "summary": {
            "files": len(bundle.file_records),
            "drift": len(drift),
        },
        "impacted_resources": [record.path for record in bundle.file_records],
        "payload": payload,
    }


def _sync_import_components(
    root: Path,
    *,
    input_dir: Path | None = None,
    fail_on_drift: bool = False,
) -> dict[str, Any]:
    source_dir = (input_dir if input_dir is not None else (root / "memory")).resolve()
    snapshot = _importer.load_import_snapshot(source_dir)
    plan = _importer.build_import_plan(root, snapshot)
    target_db_fingerprint = _current_db_fingerprint(root)
    impacted_resources = sorted(
        {
            *plan.entries.create_ids,
            *plan.entries.update_ids,
            *plan.entries.remove_ids,
            *plan.events.create_ids,
            *plan.events.update_ids,
            *plan.events.remove_ids,
            *plan.entities.create_ids,
            *plan.entities.update_ids,
            *plan.entities.remove_ids,
            *plan.edges.create_ids,
            *plan.edges.update_ids,
            *plan.edges.remove_ids,
        }
    )
    return {
        "command_id": "memory.sync.import",
        "request_hash": stable_hash(
            {
                "command_id": "memory.sync.import.plan",
                "input_dir": source_dir.as_posix(),
                "fail_on_drift": fail_on_drift,
                "source_db_fingerprint": snapshot.manifest.source_db_fingerprint,
                "target_db_fingerprint": target_db_fingerprint,
            }
        ),
        "options": {
            "input_dir": source_dir.as_posix(),
            "fail_on_drift": fail_on_drift,
        },
        "summary": dict(plan.summary),
        "impacted_resources": impacted_resources,
        "payload": plan.model_dump(mode="json"),
    }


def _current_db_fingerprint(root: Path) -> str:
    conn = _store._connect(root)
    try:
        return _export.compute_source_db_fingerprint(
            _export._load_entries(conn),
            _export._load_events(conn),
            _export._load_entities(conn),
            _export._load_edges(conn),
        )
    finally:
        conn.close()


def _write_plan(
    root: Path,
    *,
    workflow: str,
    command_id: str,
    request_hash: str,
    options: dict[str, Any],
    summary: dict[str, int],
    impacted_resources: list[str],
    payload: dict[str, Any],
    plan_out: Path | None,
) -> PlanArtifact:
    path = (plan_out if plan_out is not None else default_plan_path(root, workflow)).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact = PlanArtifact(
        workflow=workflow,
        command_id=command_id,
        created_at=_store._utc_now(),
        plan_path=path.as_posix(),
        request_hash=request_hash,
        options=options,
        summary=summary,
        impacted_resources=impacted_resources,
        payload=payload,
    )
    path.write_bytes(to_json_bytes(artifact))
    return artifact
