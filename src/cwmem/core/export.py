from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import orjson

from cwmem.core import embeddings as _emb
from cwmem.core import graph as _graph
from cwmem.core import paths as _paths
from cwmem.core import store as _store
from cwmem.core.models import (
    EdgeRecord,
    EntityRecord,
    EntryRecord,
    EventRecord,
    ExportFileRecord,
    ExportManifest,
    ExportModelInfo,
    ExportResult,
)
from cwmem.output.envelope import conflict_error

_MANIFEST_RELATIVE_PATH = "manifests/export-manifest.json"
_JSON_OPTIONS = orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS
_EPOCH = "1970-01-01T00:00:00+00:00"


@dataclass(frozen=True)
class ExportBundle:
    manifest: ExportManifest
    files: dict[str, bytes]
    file_records: list[ExportFileRecord]


def _json_inline(value: Any) -> str:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")


def _escape_quotes(value: str) -> str:
    return value.replace('"', '\\"')


def render_entry_markdown(entry: EntryRecord) -> str:
    front_matter = [
        "---",
        f'public_id: "{entry.public_id}"',
        f'internal_id: "{entry.internal_id}"',
        f'title: "{_escape_quotes(entry.title)}"',
        f'type: "{entry.type}"',
        f'status: "{entry.status}"',
        f'author: "{_escape_quotes(entry.author or "")}"',
        f'fingerprint: "{entry.fingerprint}"',
        f'created_at: "{entry.created_at}"',
        f'updated_at: "{entry.updated_at}"',
        f"tags: {_json_inline(entry.tags)}",
        f"related_ids: {_json_inline(entry.related_ids)}",
        f"entity_refs: {_json_inline(entry.entity_refs)}",
        f"provenance: {_json_inline(entry.provenance)}",
        f"metadata: {_json_inline(entry.metadata)}",
        "---",
        "",
        entry.body,
        "",
    ]
    return "\n".join(front_matter)


def render_entry_jsonl(entry: EntryRecord) -> str:
    payload = entry.model_dump(mode="json")
    return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode("utf-8") + "\n"


def render_event_jsonl(event: EventRecord) -> str:
    payload = event.model_dump(mode="json")
    return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode("utf-8") + "\n"


def render_entity_jsonl(entity: EntityRecord) -> str:
    payload = entity.model_dump(mode="json")
    return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode("utf-8") + "\n"


def render_edge_jsonl(edge: EdgeRecord) -> str:
    payload = edge.model_dump(mode="json")
    return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode("utf-8") + "\n"


def build_export_bundle(root: Path, output_dir: Path | None = None) -> ExportBundle:
    conn = _store._connect(root)
    try:
        entries = _load_entries(conn)
        events = _load_events(conn)
        entities = _load_entities(conn)
        edges = _load_edges(conn)
    finally:
        conn.close()

    taxonomy_payloads = _load_taxonomy_payloads(root)
    generated_at = _derive_generated_at(entries, events, entities, edges)
    model_info = _load_model_info(root)
    source_db_fingerprint = compute_source_db_fingerprint(entries, events, entities, edges)

    files: dict[str, bytes] = {}
    for entry in entries:
        files[f"entries/{entry.public_id}.md"] = render_entry_markdown(entry).encode("utf-8")
    files["entries/entries.jsonl"] = "".join(render_entry_jsonl(entry) for entry in entries).encode(
        "utf-8"
    )
    files["events/events.jsonl"] = "".join(render_event_jsonl(event) for event in events).encode(
        "utf-8"
    )
    files["graph/nodes.jsonl"] = "".join(render_entity_jsonl(entity) for entity in entities).encode(
        "utf-8"
    )
    files["graph/edges.jsonl"] = "".join(render_edge_jsonl(edge) for edge in edges).encode("utf-8")
    for relative_path, payload in taxonomy_payloads.items():
        files[relative_path] = _render_json_bytes(payload)

    file_hashes = {path: _sha256_digest(content) for path, content in sorted(files.items())}
    manifest = ExportManifest(
        export_version="1.0",
        source_db_fingerprint=source_db_fingerprint,
        counts={
            "entries": len(entries),
            "events": len(events),
            "entities": len(entities),
            "edges": len(edges),
            "taxonomy_files": len(taxonomy_payloads),
        },
        files=file_hashes,
        model=model_info,
        generated_at=generated_at,
    )
    manifest_self_fingerprint = _compute_manifest_self_fingerprint(manifest)
    manifest = manifest.model_copy(
        update={
            "files": {
                **manifest.files,
                _MANIFEST_RELATIVE_PATH: manifest_self_fingerprint,
            }
        }
    )
    manifest_bytes = _render_json_bytes(manifest.model_dump(mode="json"))
    files[_MANIFEST_RELATIVE_PATH] = manifest_bytes

    file_records = [
        ExportFileRecord(
            path=relative_path,
            fingerprint=_sha256_digest(content),
            size_bytes=len(content),
        )
        for relative_path, content in sorted(files.items())
    ]
    return ExportBundle(manifest=manifest, files=files, file_records=file_records)


def export_snapshot(
    root: Path,
    output_dir: Path | None = None,
    *,
    check: bool = False,
) -> ExportResult:
    bundle = build_export_bundle(root, output_dir)
    target_dir = (output_dir or (root / "memory")).resolve()
    drift = compare_export_to_disk(bundle, target_dir)
    if check:
        if drift:
            raise conflict_error(
                "Tracked sync artifacts are stale compared with the runtime snapshot.",
                details={
                    "output_dir": target_dir.as_posix(),
                    "drift": drift,
                    "source_db_fingerprint": bundle.manifest.source_db_fingerprint,
                },
            )
        return ExportResult(
            output_dir=target_dir.as_posix(),
            check=True,
            changed=False,
            files=bundle.file_records,
            manifest=bundle.manifest,
            drift=[],
        )

    _write_bundle(target_dir, bundle)
    return ExportResult(
        output_dir=target_dir.as_posix(),
        check=False,
        changed=bool(drift),
        files=bundle.file_records,
        manifest=bundle.manifest,
        drift=[],
    )


def compare_export_to_disk(bundle: ExportBundle, output_dir: Path) -> list[dict[str, Any]]:
    drift: list[dict[str, Any]] = []
    for relative_path, expected in sorted(bundle.files.items()):
        actual_path = output_dir / relative_path
        if not actual_path.is_file():
            drift.append({"path": relative_path, "reason": "missing"})
            continue
        actual = actual_path.read_bytes()
        if actual != expected:
            drift.append(
                {
                    "path": relative_path,
                    "reason": "content_mismatch",
                    "expected": _sha256_digest(expected),
                    "actual": _sha256_digest(actual),
                }
            )

    expected_entry_markdown = {
        relative_path for relative_path in bundle.files if relative_path.startswith("entries/")
    }
    entries_dir = output_dir / "entries"
    if entries_dir.is_dir():
        for candidate in sorted(entries_dir.glob("*.md")):
            relative_path = candidate.relative_to(output_dir).as_posix()
            if relative_path not in expected_entry_markdown:
                drift.append({"path": relative_path, "reason": "unexpected_file"})
    return drift


def compute_source_db_fingerprint(
    entries: list[EntryRecord],
    events: list[EventRecord],
    entities: list[EntityRecord],
    edges: list[EdgeRecord],
) -> str:
    payload = {
        "entries": [entry.model_dump(mode="json") for entry in entries],
        "events": [event.model_dump(mode="json") for event in events],
        "entities": [entity.model_dump(mode="json") for entity in entities],
        "edges": [edge.model_dump(mode="json") for edge in edges],
    }
    return _sha256_digest(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS))


def _load_entries(conn: sqlite3.Connection) -> list[EntryRecord]:
    rows = conn.execute("SELECT * FROM entries ORDER BY public_id ASC").fetchall()
    return [_store._entry_from_row(conn, row) for row in rows]


def _load_events(conn: sqlite3.Connection) -> list[EventRecord]:
    rows = conn.execute(
        "SELECT * FROM events ORDER BY occurred_at ASC, public_id ASC"
    ).fetchall()
    return [_store._event_from_row(conn, row) for row in rows]


def _load_entities(conn: sqlite3.Connection) -> list[EntityRecord]:
    rows = conn.execute("SELECT * FROM entities ORDER BY public_id ASC").fetchall()
    return [_store._entity_from_row(conn, row) for row in rows]


def _load_edges(conn: sqlite3.Connection) -> list[EdgeRecord]:
    rows = conn.execute(
        """
        SELECT *
        FROM edges
        ORDER BY is_inferred ASC, confidence DESC, relation_type ASC, public_id ASC
        """
    ).fetchall()
    return [_graph._edge_from_row(row) for row in rows]


def _load_taxonomy_payloads(root: Path) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for relative_path, seed_payload in sorted(_paths.TAXONOMY_SEEDS.items()):
        seed_data = dict(seed_payload)
        absolute_path = root / relative_path
        if absolute_path.is_file():
            raw_payload = _load_json_file(
                absolute_path,
                suggested_action="Fix the taxonomy JSON and retry `cwmem sync export`.",
            )
        else:
            raw_payload = seed_data
        items = raw_payload.get("items", [])
        if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
            _store._raise_validation(
                "Taxonomy artifacts must contain a string `items` list.",
                details={"path": relative_path},
                suggested_action="Fix the taxonomy JSON and retry `cwmem sync export`.",
            )
        normalized_items = cast(list[str], items)
        payloads[relative_path.removeprefix("memory/")] = {
            "schema_version": str(raw_payload.get("schema_version", "1.0")),
            "taxonomy": str(raw_payload.get("taxonomy", seed_data.get("taxonomy", ""))),
            "items": sorted({item.strip() for item in normalized_items if item.strip()}),
        }
    return payloads


def _load_model_info(root: Path) -> ExportModelInfo:
    manifest = _emb.load_manifest(root)
    return ExportModelInfo(
        name=manifest.model_name,
        version=manifest.model_version,
        vector_dim=manifest.vector_dim,
    )


def _derive_generated_at(
    entries: list[EntryRecord],
    events: list[EventRecord],
    entities: list[EntityRecord],
    edges: list[EdgeRecord],
) -> str:
    candidates = [
        *[entry.updated_at for entry in entries],
        *[entry.created_at for entry in entries],
        *[event.occurred_at for event in events],
        *[event.created_at for event in events],
        *[entity.updated_at for entity in entities],
        *[entity.created_at for entity in entities],
        *[edge.updated_at for edge in edges],
        *[edge.created_at for edge in edges],
    ]
    if not candidates:
        return _EPOCH
    return max(candidates)


def _render_json_bytes(payload: Any) -> bytes:
    return orjson.dumps(payload, option=_JSON_OPTIONS) + b"\n"


def _compute_manifest_self_fingerprint(manifest: ExportManifest) -> str:
    payload = manifest.model_dump(mode="json")
    payload["files"] = {
        path: fingerprint
        for path, fingerprint in payload["files"].items()
        if path != _MANIFEST_RELATIVE_PATH
    }
    return _sha256_digest(_render_json_bytes(payload))


def _load_json_file(path: Path, *, suggested_action: str) -> dict[str, Any]:
    payload: Any
    try:
        payload = orjson.loads(path.read_bytes())
    except orjson.JSONDecodeError:
        _store._raise_validation(
            "Malformed JSON artifact encountered during export.",
            details={"path": path.as_posix()},
            suggested_action=suggested_action,
        )
    if not isinstance(payload, dict):
        _store._raise_validation(
            "JSON artifacts must decode to an object.",
            details={"path": path.as_posix()},
            suggested_action=suggested_action,
        )
    return cast(dict[str, Any], payload)


def _write_bundle(output_dir: Path, bundle: ExportBundle) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for relative_dir in ("entries", "events", "graph", "taxonomy", "manifests"):
        (output_dir / relative_dir).mkdir(parents=True, exist_ok=True)

    expected_entry_markdown = {
        relative_path for relative_path in bundle.files if relative_path.startswith("entries/")
    }
    entries_dir = output_dir / "entries"
    for candidate in sorted(entries_dir.glob("*.md")):
        relative_path = candidate.relative_to(output_dir).as_posix()
        if relative_path not in expected_entry_markdown:
            candidate.unlink()

    for relative_path, content in sorted(bundle.files.items()):
        absolute_path = output_dir / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_bytes(content)


def _sha256_digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
