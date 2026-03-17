from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import orjson
from pydantic import ValidationError

from cwmem.core import embeddings as _emb
from cwmem.core import export as _export
from cwmem.core import fts as _fts
from cwmem.core import graph as _graph
from cwmem.core import paths as _paths
from cwmem.core import store as _store
from cwmem.core.fingerprints import (
    compute_edge_fingerprint,
    compute_entity_fingerprint,
    compute_entry_fingerprint,
    compute_event_fingerprint,
)
from cwmem.core.models import (
    EdgeRecord,
    EntityRecord,
    EntryRecord,
    EventRecord,
    ExportManifest,
    ExportModelInfo,
    ImportChangeSet,
    ImportPlan,
    ImportResult,
)

_MANIFEST_PATH = Path("manifests") / "export-manifest.json"
_SEQUENTIAL_ID_RE = re.compile(r"^(?P<prefix>mem|evt|ent|edg)-(?P<number>\d{6})$")


@dataclass(frozen=True)
class ImportedSnapshot:
    source_dir: Path
    manifest: ExportManifest
    entries: list[EntryRecord]
    events: list[EventRecord]
    entities: list[EntityRecord]
    edges: list[EdgeRecord]
    explicit_edges: list[EdgeRecord]
    inferred_edges: list[EdgeRecord]
    taxonomy: dict[str, dict[str, Any]]


def import_snapshot(
    root: Path,
    source_dir: Path | None = None,
    *,
    dry_run: bool = False,
) -> ImportResult:
    snapshot = load_import_snapshot(source_dir or (root / "memory"))
    plan = build_import_plan(root, snapshot)
    if dry_run:
        return ImportResult(
            dry_run=True,
            applied=False,
            source_dir=snapshot.source_dir.as_posix(),
            plan=plan,
            rebuilt={},
        )

    rebuilt = apply_import_plan(root, snapshot)
    return ImportResult(
        dry_run=False,
        applied=True,
        source_dir=snapshot.source_dir.as_posix(),
        plan=plan,
        rebuilt=rebuilt,
    )


def load_import_snapshot(source_dir: Path) -> ImportedSnapshot:
    resolved_dir = source_dir.resolve()
    manifest_path = resolved_dir / _MANIFEST_PATH

    entries = _load_jsonl_records(resolved_dir / "entries" / "entries.jsonl", EntryRecord)
    events = _load_jsonl_records(resolved_dir / "events" / "events.jsonl", EventRecord)
    entities = _load_jsonl_records(resolved_dir / "graph" / "nodes.jsonl", EntityRecord)
    edges = _load_jsonl_records(resolved_dir / "graph" / "edges.jsonl", EdgeRecord)
    taxonomy = _load_taxonomy_payloads(resolved_dir)

    _validate_unique_records(entries, "entry")
    _validate_unique_records(events, "event")
    _validate_unique_records(entities, "entity")
    _validate_unique_records(edges, "edge")
    _validate_fingerprints(entries, events, entities, edges)

    if manifest_path.is_file():
        manifest = _load_json_object(manifest_path, ExportManifest)
        _validate_manifest_integrity(manifest, resolved_dir)
        _validate_counts(manifest, entries, events, entities, edges, taxonomy)
        _validate_snapshot_fingerprint(manifest, entries, events, entities, edges)
    else:
        manifest = _synthesize_manifest(entries, events, entities, edges, taxonomy)

    explicit_edges = [edge for edge in edges if not edge.is_inferred]
    inferred_edges = [edge for edge in edges if edge.is_inferred]
    snapshot = ImportedSnapshot(
        source_dir=resolved_dir,
        manifest=manifest,
        entries=entries,
        events=events,
        entities=entities,
        edges=edges,
        explicit_edges=explicit_edges,
        inferred_edges=inferred_edges,
        taxonomy=taxonomy,
    )
    _validate_import_references(snapshot)
    return snapshot


def build_import_plan(root: Path, snapshot: ImportedSnapshot) -> ImportPlan:
    conn = _store._connect(root)
    try:
        existing_entries = {
            record.public_id: record.fingerprint for record in _export._load_entries(conn)
        }
        existing_events = {
            record.public_id: record.fingerprint for record in _export._load_events(conn)
        }
        existing_entities = {
            record.public_id: record.fingerprint for record in _export._load_entities(conn)
        }
        existing_edges = {
            record.public_id: record.fingerprint for record in _export._load_edges(conn)
        }
    finally:
        conn.close()

    entry_changes = _diff_records(
        existing_entries, {record.public_id: record.fingerprint for record in snapshot.entries}
    )
    event_changes = _diff_records(
        existing_events, {record.public_id: record.fingerprint for record in snapshot.events}
    )
    entity_changes = _diff_records(
        existing_entities, {record.public_id: record.fingerprint for record in snapshot.entities}
    )
    edge_changes = _diff_records(
        existing_edges, {record.public_id: record.fingerprint for record in snapshot.edges}
    )
    summary = _summarize_plan(
        entries=entry_changes,
        events=event_changes,
        entities=entity_changes,
        edges=edge_changes,
    )
    return ImportPlan(
        source_dir=snapshot.source_dir.as_posix(),
        source_db_fingerprint=snapshot.manifest.source_db_fingerprint,
        generated_at=snapshot.manifest.generated_at,
        entries=entry_changes,
        events=event_changes,
        entities=entity_changes,
        edges=edge_changes,
        summary=summary,
    )


def apply_import_plan(root: Path, snapshot: ImportedSnapshot) -> dict[str, int]:
    _store.ensure_schema(root)
    conn = _store._connect(root)
    try:
        with conn:
            _clear_runtime_tables(conn)
            for entity in snapshot.entities:
                _insert_entity(conn, entity)
            for entry in snapshot.entries:
                _store._insert_entry(conn, entry)
            for event in snapshot.events:
                _insert_event(conn, event)
            for edge in snapshot.explicit_edges:
                _graph._insert_edge(conn, edge)

            _set_counter(conn, "next_mem_id", snapshot.entries, "mem")
            _set_counter(conn, "next_evt_id", snapshot.events, "evt")
            _set_counter(conn, "next_ent_id", snapshot.entities, "ent")
            _set_counter(conn, "next_edg_id", snapshot.explicit_edges, "edg")

            inferred_count = _graph.rebuild_inferred_edges(conn)
            entry_count, event_count = _fts.rebuild_fts(conn)
            embedding_count = _emb.rebuild_embeddings(root, conn)
            conn.execute(
                """
                INSERT INTO metadata(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("last_build_at", _store._utc_now()),
            )

            rebuilt_edges = _export._load_edges(conn)
            actual_fingerprints = {
                record.public_id: record.fingerprint for record in rebuilt_edges
            }
            expected_fingerprints = {
                record.public_id: record.fingerprint for record in snapshot.edges
            }
            if actual_fingerprints != expected_fingerprints:
                _store._raise_validation(
                    "Imported graph edges do not match the inferred export snapshot.",
                    details={
                        "expected_edge_ids": sorted(expected_fingerprints),
                        "actual_edge_ids": sorted(actual_fingerprints),
                    },
                    suggested_action=(
                        "Re-run `cwmem sync export` from the source repository, "
                        "then retry the import."
                    ),
                )

        return {
            "entry_fts": entry_count,
            "event_fts": event_count,
            "embeddings": embedding_count,
            "inferred_edges": inferred_count,
        }
    finally:
        conn.close()


def _validate_manifest_integrity(manifest: ExportManifest, resolved_dir: Path) -> None:
    expected_required = {
        "entries/entries.jsonl",
        "events/events.jsonl",
        "graph/nodes.jsonl",
        "graph/edges.jsonl",
        *[relative.removeprefix("memory/") for relative in _paths.TAXONOMY_SEEDS],
    }
    missing_required = sorted(expected_required - set(manifest.files))
    if missing_required:
        _store._raise_validation(
            "Export manifest is missing required artifact records.",
            details={"missing_files": missing_required},
            suggested_action="Re-run `cwmem sync export` to regenerate the manifest.",
        )

    for relative_path, expected_fingerprint in sorted(manifest.files.items()):
        artifact_path = _resolve_artifact_path(resolved_dir, relative_path)
        if not artifact_path.is_file():
            _store._raise_validation(
                "An artifact declared in the manifest does not exist.",
                details={"path": relative_path},
                suggested_action="Repair the `memory/` tree and retry the import.",
            )
        if relative_path == _MANIFEST_PATH.as_posix():
            actual_fingerprint = _export._compute_manifest_self_fingerprint(manifest)
        else:
            actual_fingerprint = _export._sha256_digest(artifact_path.read_bytes())
        if actual_fingerprint != expected_fingerprint:
            _store._raise_validation(
                "An artifact fingerprint does not match the manifest.",
                details={
                    "path": relative_path,
                    "expected_fingerprint": expected_fingerprint,
                    "actual_fingerprint": actual_fingerprint,
                },
                suggested_action="Re-run `cwmem sync export` or revert the edited artifact.",
            )


def _synthesize_manifest(
    entries: list[EntryRecord],
    events: list[EventRecord],
    entities: list[EntityRecord],
    edges: list[EdgeRecord],
    taxonomy: dict[str, dict[str, Any]],
) -> ExportManifest:
    return ExportManifest(
        export_version="1.0",
        source_db_fingerprint=_export.compute_source_db_fingerprint(
            entries, events, entities, edges
        ),
        counts={
            "entries": len(entries),
            "events": len(events),
            "entities": len(entities),
            "edges": len(edges),
            "taxonomy_files": len(taxonomy),
        },
        files={},
        model=ExportModelInfo(name="", version="", vector_dim=0),
        generated_at=_export._derive_generated_at(entries, events, entities, edges),
    )


def _load_jsonl_records(path: Path, model_type: type[Any]) -> list[Any]:
    if not path.is_file():
        _store._raise_validation(
            "A required JSONL artifact is missing.",
            details={"path": path.as_posix()},
            suggested_action="Regenerate the export surface and retry the import.",
        )
    records = [
        _load_json_line(path, line, model_type)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return sorted(records, key=_sort_key)


def _load_taxonomy_payloads(source_dir: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for relative_path in sorted(_paths.TAXONOMY_SEEDS):
        artifact_path = source_dir / relative_path.removeprefix("memory/")
        payload = _load_json_object(artifact_path)
        items = payload.get("items", [])
        if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
            _store._raise_validation(
                "Taxonomy artifacts must contain a string `items` list.",
                details={"path": artifact_path.as_posix()},
                suggested_action="Fix the taxonomy JSON and retry the import.",
            )
        payloads[relative_path.removeprefix("memory/")] = {
            "schema_version": str(payload.get("schema_version", "1.0")),
            "taxonomy": str(payload.get("taxonomy", "")),
            "items": sorted({item.strip() for item in items if item.strip()}),
        }
    return payloads


def _resolve_artifact_path(source_dir: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        _store._raise_validation(
            "Manifest artifact paths must be relative to the import surface.",
            details={"path": relative_path},
            suggested_action="Regenerate the export manifest and retry the import.",
        )
    resolved = (source_dir / candidate).resolve()
    if not resolved.is_relative_to(source_dir):
        _store._raise_validation(
            "Manifest artifact paths cannot escape the import surface.",
            details={"path": relative_path},
            suggested_action="Regenerate the export manifest and retry the import.",
        )
    return resolved


def _validate_import_references(snapshot: ImportedSnapshot) -> None:
    known_ids = {
        record.public_id: "entry" for record in snapshot.entries
    } | {record.public_id: "event" for record in snapshot.events} | {
        record.public_id: "entity" for record in snapshot.entities
    }

    for entry in snapshot.entries:
        for entity_ref in entry.entity_refs:
            _validate_known_resource(
                known_ids,
                entity_ref,
                expected_kind="entity",
                context=f"entry {entry.public_id}",
            )

    for event in snapshot.events:
        for resource in event.resources:
            _validate_known_resource(
                known_ids,
                resource.resource_id,
                expected_kind=None,
                context=f"event {event.public_id}",
            )
        for entity_ref in event.entity_refs:
            _validate_known_resource(
                known_ids,
                entity_ref,
                expected_kind="entity",
                context=f"event {event.public_id}",
            )

    for edge in snapshot.explicit_edges:
        _validate_known_resource(
            known_ids,
            edge.source_id,
            expected_kind=edge.source_type,
            context=f"edge {edge.public_id}",
        )
        _validate_known_resource(
            known_ids,
            edge.target_id,
            expected_kind=edge.target_type,
            context=f"edge {edge.public_id}",
        )

    for edge in snapshot.inferred_edges:
        _validate_known_resource(
            known_ids,
            edge.source_id,
            expected_kind="entry",
            context=f"inferred edge {edge.public_id}",
        )
        _validate_known_resource(
            known_ids,
            edge.target_id,
            expected_kind="entry",
            context=f"inferred edge {edge.public_id}",
        )


def _load_json_object(path: Path, model_type: type[Any] | None = None) -> Any:
    payload: Any
    try:
        payload = orjson.loads(path.read_bytes())
    except orjson.JSONDecodeError:
        _store._raise_validation(
            "Malformed JSON artifact encountered during import.",
            details={"path": path.as_posix()},
            suggested_action="Repair the JSON artifact and retry the import.",
        )
    if model_type is None:
        if not isinstance(payload, dict):
            _store._raise_validation(
                "JSON artifacts must decode to an object.",
                details={"path": path.as_posix()},
                suggested_action="Repair the JSON artifact and retry the import.",
            )
        return cast(dict[str, Any], payload)
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        _store._raise_validation(
            "JSON artifact does not match the expected schema.",
            details={"path": path.as_posix(), "validation_errors": exc.errors()},
            suggested_action="Regenerate the sync artifacts and retry the import.",
        )
    raise AssertionError("unreachable")


def _load_json_line(path: Path, line: str, model_type: type[Any]) -> Any:
    payload: Any
    try:
        payload = orjson.loads(line)
    except orjson.JSONDecodeError:
        _store._raise_validation(
            "Malformed JSONL artifact encountered during import.",
            details={"path": path.as_posix()},
            suggested_action="Repair the JSONL artifact and retry the import.",
        )
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        _store._raise_validation(
            "JSONL artifact record does not match the expected schema.",
            details={"path": path.as_posix(), "validation_errors": exc.errors()},
            suggested_action="Regenerate the sync artifacts and retry the import.",
        )
    raise AssertionError("unreachable")


def _validate_fingerprints(
    entries: list[EntryRecord],
    events: list[EventRecord],
    entities: list[EntityRecord],
    edges: list[EdgeRecord],
) -> None:
    for record in entries:
        if record.fingerprint != compute_entry_fingerprint(record):
            _raise_record_validation("entry", record.public_id)
    for record in events:
        if record.fingerprint != compute_event_fingerprint(record):
            _raise_record_validation("event", record.public_id)
    for record in entities:
        if record.fingerprint != compute_entity_fingerprint(record):
            _raise_record_validation("entity", record.public_id)
    for record in edges:
        if record.fingerprint != compute_edge_fingerprint(record):
            _raise_record_validation("edge", record.public_id)


def _validate_counts(
    manifest: ExportManifest,
    entries: list[EntryRecord],
    events: list[EventRecord],
    entities: list[EntityRecord],
    edges: list[EdgeRecord],
    taxonomy: dict[str, dict[str, Any]],
) -> None:
    actual_counts = {
        "entries": len(entries),
        "events": len(events),
        "entities": len(entities),
        "edges": len(edges),
        "taxonomy_files": len(taxonomy),
    }
    for key, actual_value in actual_counts.items():
        expected_value = manifest.counts.get(key)
        if expected_value != actual_value:
            _store._raise_validation(
                "Manifest counts do not match the import artifacts.",
                details={"field": key, "expected": expected_value, "actual": actual_value},
                suggested_action="Re-run `cwmem sync export` to refresh the manifest.",
            )


def _validate_snapshot_fingerprint(
    manifest: ExportManifest,
    entries: list[EntryRecord],
    events: list[EventRecord],
    entities: list[EntityRecord],
    edges: list[EdgeRecord],
) -> None:
    actual = _export.compute_source_db_fingerprint(entries, events, entities, edges)
    if actual != manifest.source_db_fingerprint:
        _store._raise_validation(
            "The exported data does not match the manifest snapshot fingerprint.",
            details={
                "expected_fingerprint": manifest.source_db_fingerprint,
                "actual_fingerprint": actual,
            },
            suggested_action="Re-run `cwmem sync export` and retry the import.",
        )


def _diff_records(
    existing: dict[str, str],
    incoming: dict[str, str],
) -> ImportChangeSet:
    create_ids = sorted(resource_id for resource_id in incoming if resource_id not in existing)
    update_ids = sorted(
        resource_id
        for resource_id, fingerprint in incoming.items()
        if resource_id in existing and existing[resource_id] != fingerprint
    )
    remove_ids = sorted(resource_id for resource_id in existing if resource_id not in incoming)
    unchanged_ids = sorted(
        resource_id
        for resource_id, fingerprint in incoming.items()
        if resource_id in existing and existing[resource_id] == fingerprint
    )
    return ImportChangeSet(
        create_ids=create_ids,
        update_ids=update_ids,
        remove_ids=remove_ids,
        unchanged_ids=unchanged_ids,
    )


def _summarize_plan(**changes: ImportChangeSet) -> dict[str, int]:
    summary: dict[str, int] = {}
    for prefix, change_set in changes.items():
        summary[f"{prefix}_create"] = len(change_set.create_ids)
        summary[f"{prefix}_update"] = len(change_set.update_ids)
        summary[f"{prefix}_remove"] = len(change_set.remove_ids)
        summary[f"{prefix}_unchanged"] = len(change_set.unchanged_ids)
    return summary


def _clear_runtime_tables(conn: sqlite3.Connection) -> None:
    for table_name in (
        "entry_tags",
        "event_tags",
        "event_resources",
        "entity_tags",
        "entries_fts",
        "events_fts",
        "entities_fts",
        "embeddings",
        "edges",
        "events",
        "entities",
        "entries",
    ):
        conn.execute(f"DELETE FROM {table_name}")  # noqa: S608


def _insert_event(conn: sqlite3.Connection, record: EventRecord) -> None:
    conn.execute(
        """
        INSERT INTO events(
            internal_id,
            public_id,
            event_type,
            body,
            author,
            occurred_at,
            created_at,
            related_ids_json,
            entity_refs_json,
            metadata_json,
            fingerprint
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.internal_id,
            record.public_id,
            record.event_type,
            record.body,
            record.author,
            record.occurred_at,
            record.created_at,
            _store._json_dump(record.related_ids),
            _store._json_dump(record.entity_refs),
            _store._json_dump(record.metadata),
            record.fingerprint,
        ),
    )
    conn.executemany(
        "INSERT OR IGNORE INTO event_tags(event_internal_id, tag, created_at) VALUES (?, ?, ?)",
        [(record.internal_id, tag, record.created_at) for tag in record.tags],
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO event_resources(event_internal_id, resource_public_id, role)
        VALUES (?, ?, ?)
        """,
        [
            (record.internal_id, resource.resource_id, resource.role)
            for resource in record.resources
        ],
    )


def _insert_entity(conn: sqlite3.Connection, record: EntityRecord) -> None:
    conn.execute(
        """
        INSERT INTO entities(
            internal_id,
            public_id,
            entity_type,
            name,
            description,
            status,
            aliases_json,
            provenance_json,
            metadata_json,
            fingerprint,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.internal_id,
            record.public_id,
            record.entity_type,
            record.name,
            record.description,
            record.status,
            _store._json_dump(record.aliases),
            _store._json_dump(record.provenance),
            _store._json_dump(record.metadata),
            record.fingerprint,
            record.created_at,
            record.updated_at,
        ),
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO entity_tags(entity_internal_id, tag, created_at)
        VALUES (?, ?, ?)
        """,
        [(record.internal_id, tag, record.created_at) for tag in record.tags],
    )
    _fts.upsert_entity_fts(conn, record)


def _set_counter(
    conn: sqlite3.Connection,
    metadata_key: str,
    records: list[Any],
    prefix: str,
) -> None:
    next_number = 1
    for record in records:
        match = _SEQUENTIAL_ID_RE.match(record.public_id)
        if match and match.group("prefix") == prefix:
            next_number = max(next_number, int(match.group("number")) + 1)
    conn.execute(
        """
        INSERT INTO metadata(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (metadata_key, str(next_number)),
    )


def _sort_key(record: Any) -> tuple[Any, ...]:
    if isinstance(record, EntryRecord):
        return (record.public_id,)
    if isinstance(record, EventRecord):
        return (record.occurred_at, record.public_id)
    if isinstance(record, EntityRecord):
        return (record.public_id,)
    if isinstance(record, EdgeRecord):
        return (
            int(record.is_inferred),
            -int(round(record.confidence * 1_000_000)),
            record.relation_type,
            record.public_id,
        )
    return ("",)


def _raise_record_validation(kind: str, public_id: str) -> None:
    _store._raise_validation(
        "An imported record fingerprint does not match its canonical payload.",
        details={"resource_kind": kind, "resource_id": public_id},
        suggested_action="Regenerate the export artifacts and retry the import.",
    )


def _validate_known_resource(
    known_ids: dict[str, str],
    resource_id: str,
    *,
    expected_kind: str | None,
    context: str,
) -> None:
    actual_kind = known_ids.get(resource_id)
    if actual_kind is None:
        _store._raise_validation(
            "Imported artifacts reference a resource that is not present in the snapshot.",
            details={"resource_id": resource_id, "context": context},
            suggested_action="Repair the artifact references and retry the import.",
        )
    if expected_kind is not None and actual_kind != expected_kind:
        _store._raise_validation(
            "Imported artifact reference type does not match the referenced resource.",
            details={
                "resource_id": resource_id,
                "expected_kind": expected_kind,
                "actual_kind": actual_kind,
                "context": context,
            },
            suggested_action="Repair the artifact references and retry the import.",
        )


def _validate_unique_records(records: list[Any], resource_kind: str) -> None:
    _validate_unique_field(records, resource_kind, "public_id")
    _validate_unique_field(records, resource_kind, "internal_id")


def _validate_unique_field(records: list[Any], resource_kind: str, field_name: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for record in records:
        value = getattr(record, field_name)
        if value in seen:
            duplicates.add(value)
            continue
        seen.add(value)
    if duplicates:
        _store._raise_validation(
            "Imported artifacts contain duplicate identifiers.",
            details={
                "resource_kind": resource_kind,
                "field": field_name,
                "duplicates": sorted(duplicates),
            },
            suggested_action="Deduplicate the artifact records and retry the import.",
        )
