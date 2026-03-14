from __future__ import annotations

from pathlib import Path

from cwmem.core import export as _export
from cwmem.core import planner as _planner
from cwmem.core import store as _store
from cwmem.core.models import ExportManifest, ValidationIssue, ValidationResult, VerificationResult


def validate_repository(root: Path) -> ValidationResult:
    conn = _store._connect(root)
    try:
        issues = list(_store.validate_index(root).issues)
        issues.extend(_reference_issues(conn))
        issues.extend(_taxonomy_issues(root, conn))
        issues.extend(_duplicate_id_issues(conn))
        issues.extend(_export_drift_issues(root))
        return ValidationResult(ok=not issues, issues=issues)
    finally:
        conn.close()


def verify_repository(root: Path, *, plan_path: Path | None = None) -> VerificationResult:
    validation = validate_repository(root)
    issues = list(validation.issues)
    checks: dict[str, bool] = {}
    stats = _store.get_stats(root)

    checks["fts_counts_match"] = (
        stats.entries == stats.entries_fts
        and stats.events == stats.events_fts
        and stats.entities == stats.entities_fts
    )
    checks["embedding_model_present"] = bool(stats.embedding_model)
    if not checks["fts_counts_match"]:
        issues.append(
            ValidationIssue(
                code="verify.fts_counts_mismatch",
                message="FTS row counts do not match the canonical tables.",
                details=stats.model_dump(mode="json"),
            )
        )
    if not checks["embedding_model_present"]:
        issues.append(
            ValidationIssue(
                code="verify.embedding_model_missing",
                message="Embedding model metadata is missing from the repository.",
                details={},
            )
        )

    manifest_path = root / "memory" / "manifests" / "export-manifest.json"
    if manifest_path.is_file():
        bundle = _export.build_export_bundle(root, root / "memory")
        manifest = ExportManifest.model_validate(
            _store._json_load(manifest_path.read_text(encoding="utf-8"))
        )
        checks["export_matches_db"] = (
            manifest.source_db_fingerprint == bundle.manifest.source_db_fingerprint
        )
        checks["manifest_matches_disk"] = manifest.files == bundle.manifest.files
        checks["graph_edge_counts_match"] = manifest.counts.get("edges") == stats.edges
        checks["embedding_model_matches_manifest"] = manifest.model.name == stats.embedding_model
        if not checks["export_matches_db"]:
            issues.append(
                ValidationIssue(
                    code="verify.export_db_fingerprint_mismatch",
                    message=(
                        "The exported manifest fingerprint does not match the current "
                        "database."
                    ),
                    details={
                        "expected": manifest.source_db_fingerprint,
                        "actual": bundle.manifest.source_db_fingerprint,
                    },
                )
            )
        if not checks["manifest_matches_disk"]:
            issues.append(
                ValidationIssue(
                    code="verify.manifest_file_mismatch",
                    message=(
                        "The manifest file inventory does not match the deterministic "
                        "export bundle."
                    ),
                    details={},
                )
            )
        if not checks["graph_edge_counts_match"]:
            issues.append(
                ValidationIssue(
                    code="verify.edge_count_mismatch",
                    message="The manifest edge count does not match the runtime graph.",
                    details={
                        "expected": manifest.counts.get("edges"),
                        "actual": stats.edges,
                    },
                )
            )
        if not checks["embedding_model_matches_manifest"]:
            issues.append(
                ValidationIssue(
                    code="verify.embedding_model_mismatch",
                    message=(
                        "The exported manifest model metadata does not match the runtime "
                        "metadata."
                    ),
                    details={
                        "expected": manifest.model.name,
                        "actual": stats.embedding_model,
                    },
                )
            )
    else:
        checks["export_matches_db"] = False
        checks["manifest_matches_disk"] = False
        checks["graph_edge_counts_match"] = False
        checks["embedding_model_matches_manifest"] = False
        issues.append(
            ValidationIssue(
                code="verify.export_manifest_missing",
                message=(
                    "The deterministic export manifest is missing; run "
                    "`cwmem sync export` first."
                ),
                details={"path": manifest_path.as_posix()},
            )
        )

    if plan_path is not None:
        plan_validation = _planner.validate_plan(root, plan_path.resolve())
        checks["plan_matches_current_state"] = plan_validation.ok
        issues.extend(plan_validation.issues)

    return VerificationResult(ok=not issues, issues=issues, checks=checks, stats=stats)


def _reference_issues(conn) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    known_ids = {row["public_id"] for row in conn.execute("SELECT public_id FROM entries")} | {
        row["public_id"] for row in conn.execute("SELECT public_id FROM events")
    } | {row["public_id"] for row in conn.execute("SELECT public_id FROM entities")}

    for row in conn.execute(
        "SELECT public_id, entity_refs_json FROM entries ORDER BY public_id ASC"
    ):
        for entity_ref in _store._json_load(row["entity_refs_json"]):
            if entity_ref not in known_ids or not str(entity_ref).startswith("ent-"):
                issues.append(
                    ValidationIssue(
                        code="validate.entry_entity_ref_invalid",
                        message="An entry references a missing or invalid entity.",
                        details={
                            "resource_id": row["public_id"],
                            "entity_ref": entity_ref,
                        },
                    )
                )

    for row in conn.execute(
        """
        SELECT e.public_id, e.entity_refs_json, r.resource_public_id
        FROM events e
        LEFT JOIN event_resources r ON r.event_internal_id = e.internal_id
        ORDER BY e.public_id ASC
        """
    ):
        if row["resource_public_id"] is not None and row["resource_public_id"] not in known_ids:
            issues.append(
                ValidationIssue(
                    code="validate.event_resource_missing",
                    message="An event references a missing resource.",
                    details={
                        "resource_id": row["public_id"],
                        "related_resource_id": row["resource_public_id"],
                    },
                )
            )
        for entity_ref in _store._json_load(row["entity_refs_json"]):
            if entity_ref not in known_ids or not str(entity_ref).startswith("ent-"):
                issues.append(
                    ValidationIssue(
                        code="validate.event_entity_ref_invalid",
                        message="An event references a missing or invalid entity.",
                        details={
                            "resource_id": row["public_id"],
                            "entity_ref": entity_ref,
                        },
                    )
                )

    for row in conn.execute(
        """
        SELECT public_id, source_id, source_type, target_id, target_type
        FROM edges
        ORDER BY public_id ASC
        """
    ):
        resource_pairs = (
            ("source_id", row["source_type"]),
            ("target_id", row["target_type"]),
        )
        for field_name, expected_kind in resource_pairs:
            resource_id = row[field_name]
            if resource_id not in known_ids:
                issues.append(
                    ValidationIssue(
                        code="validate.edge_resource_missing",
                        message="An edge references a missing resource.",
                        details={"edge_id": row["public_id"], "resource_id": resource_id},
                    )
                )
                continue
            actual_kind = _store._resource_kind(resource_id)
            if actual_kind != expected_kind:
                issues.append(
                    ValidationIssue(
                        code="validate.edge_resource_type_mismatch",
                        message=(
                            "An edge resource type does not match the referenced "
                            "resource."
                        ),
                        details={
                            "edge_id": row["public_id"],
                            "resource_id": resource_id,
                            "expected": expected_kind,
                            "actual": actual_kind,
                        },
                    )
                )
    return issues


def _taxonomy_issues(root: Path, conn) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    taxonomy = _export._load_taxonomy_payloads(root)
    entity_types = set(taxonomy["taxonomy/entity-types.json"]["items"])
    relation_types = set(taxonomy["taxonomy/relation-types.json"]["items"])

    for row in conn.execute("SELECT public_id, entity_type FROM entities ORDER BY public_id ASC"):
        if row["entity_type"] not in entity_types:
            issues.append(
                ValidationIssue(
                    code="validate.entity_type_unknown",
                    message="An entity uses a type that is not present in the taxonomy.",
                    details={
                        "resource_id": row["public_id"],
                        "entity_type": row["entity_type"],
                    },
                )
            )

    for row in conn.execute("SELECT public_id, relation_type FROM edges ORDER BY public_id ASC"):
        if row["relation_type"] not in relation_types:
            issues.append(
                ValidationIssue(
                    code="validate.relation_type_unknown",
                    message="An edge uses a relation type that is not present in the taxonomy.",
                    details={
                        "resource_id": row["public_id"],
                        "relation_type": row["relation_type"],
                    },
                )
            )
    return issues


def _duplicate_id_issues(conn) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for table_name in ("entries", "events", "entities", "edges"):
        rows = conn.execute(
            f"""
            SELECT public_id, COUNT(*) AS row_count
            FROM {table_name}
            GROUP BY public_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for row in rows:
            issues.append(
                ValidationIssue(
                    code="validate.duplicate_public_id",
                    message="A canonical table contains duplicate public IDs.",
                    details={
                        "table": table_name,
                        "public_id": row["public_id"],
                        "row_count": row["row_count"],
                    },
                )
            )
    return issues


def _export_drift_issues(root: Path) -> list[ValidationIssue]:
    manifest_path = root / "memory" / "manifests" / "export-manifest.json"
    if not manifest_path.is_file():
        return []
    bundle = _export.build_export_bundle(root, root / "memory")
    drift = _export.compare_export_to_disk(bundle, root / "memory")
    if not drift:
        return []
    return [
        ValidationIssue(
            code="validate.export_drift",
            message=(
                "The tracked export artifacts are stale compared with the runtime "
                "snapshot."
            ),
            details={"drift": drift},
        )
    ]
