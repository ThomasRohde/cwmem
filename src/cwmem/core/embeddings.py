"""Embedding adapter for the vendored Model2Vec model."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import numpy as np
from model2vec import StaticModel

from cwmem.core.models import ModelManifest, ValidationIssue

_REPO_MODEL_RELATIVE = Path("models") / "model2vec"
_MANIFEST_NAME = "manifest.json"
_REQUIRED_MODEL_FILES = ("config.json", "model.safetensors", "tokenizer.json")


def embedded_model_source() -> Path:
    """Return the bundled default model directory shipped with cwmem."""
    package_root = Path(__file__).resolve().parents[1]
    repo_root = Path(__file__).resolve().parents[3]
    candidates = (
        package_root / "vendor" / "model2vec",
        repo_root / "models" / "model2vec",
    )
    for candidate in candidates:
        if _model_bundle_complete(candidate):
            return candidate
    expected = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(
        "cwmem could not find its bundled Model2Vec payload. "
        f"Expected a complete bundle at one of: {expected}."
    )


def repo_model_dir(root: Path) -> Path:
    return root / _REPO_MODEL_RELATIVE


def repo_manifest_path(root: Path) -> Path:
    return repo_model_dir(root) / _MANIFEST_NAME


def ensure_repo_model(root: Path) -> Path:
    """Copy the bundled default model into the target repo if it is missing."""
    target = repo_model_dir(root)
    if _model_bundle_complete(target):
        return target

    source = embedded_model_source()
    target.mkdir(parents=True, exist_ok=True)
    _copy_tree_contents(source, target)

    if not _model_bundle_complete(target):
        raise FileNotFoundError(
            f"cwmem could not seed a complete repo-local model bundle at {target}."
        )
    return target


def load_manifest(root: Path) -> ModelManifest:
    """Load and validate the model manifest from the repository root."""
    manifest_path = ensure_repo_model(root) / _MANIFEST_NAME
    with manifest_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return ModelManifest.model_validate(data)


def load_vendored_model(root_or_manifest: Path) -> StaticModel:
    """Load the repo-local StaticModel recorded in the manifest.

    ``root_or_manifest`` may be a repository root directory (the manifest is
    resolved at ``root / models/model2vec/manifest.json``) or the direct path
    to a ``manifest.json`` file.
    """
    if root_or_manifest.is_file() or root_or_manifest.suffix == ".json":
        # Caller passed the manifest file directly
        manifest_path = root_or_manifest
        model_root = manifest_path.parent
        with manifest_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        manifest = ModelManifest.model_validate(data)
        model_dir = model_root / manifest.model_path
    else:
        # Caller passed a repo root directory
        model_root = ensure_repo_model(root_or_manifest)
        manifest = load_manifest(root_or_manifest)
        model_dir = model_root / manifest.model_path
    if not _model_payload_complete(model_dir):
        raise FileNotFoundError(
            f"Vendored model directory not found or incomplete at {model_dir}. "
            "Ensure models/model2vec/model/ contains config.json, tokenizer.json, "
            "and model.safetensors."
        )
    return StaticModel.from_pretrained(model_dir)


def _build_entry_text(row: sqlite3.Row) -> str:
    return f"{row['title']}\n\n{row['body']}".strip()


def _build_event_text(row: sqlite3.Row) -> str:
    return row["body"]


def ensure_embeddings_schema(conn: sqlite3.Connection) -> None:
    """Create the embeddings table if it does not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            resource_id         TEXT NOT NULL,
            resource_type       TEXT NOT NULL,
            fingerprint         TEXT NOT NULL,
            content_fingerprint TEXT NOT NULL,
            model_version       TEXT NOT NULL,
            vector_blob         BLOB NOT NULL,
            PRIMARY KEY (resource_id, resource_type)
        )
        """
    )


def rebuild_embeddings(root: Path, conn: sqlite3.Connection) -> int:
    """Embed all entries and events, skipping unchanged rows.

    Returns the number of rows written or refreshed during the rebuild.
    """
    manifest = load_manifest(root)
    model = load_vendored_model(root)
    model_version = manifest.model_version

    ensure_embeddings_schema(conn)

    entry_rows = conn.execute(
        "SELECT public_id, title, body, fingerprint FROM entries ORDER BY public_id ASC"
    ).fetchall()
    event_rows = conn.execute(
        "SELECT public_id, body, fingerprint FROM events ORDER BY public_id ASC"
    ).fetchall()

    _delete_orphan_rows(conn)

    written = 0

    def _upsert(resource_id: str, resource_type: str, text: str, fingerprint: str) -> None:
        nonlocal written
        existing = conn.execute(
            """
            SELECT content_fingerprint, model_version
            FROM embeddings
            WHERE resource_id = ? AND resource_type = ?
            """,
            (resource_id, resource_type),
        ).fetchone()
        if existing and existing[0] == fingerprint and existing[1] == model_version:
            return

        vector = _normalize_vector(model.encode([text])[0].astype(np.float32))
        conn.execute(
            """
            INSERT INTO embeddings(
                resource_id,
                resource_type,
                fingerprint,
                content_fingerprint,
                model_version,
                vector_blob
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(resource_id, resource_type)
            DO UPDATE SET
                fingerprint = excluded.fingerprint,
                content_fingerprint = excluded.content_fingerprint,
                model_version = excluded.model_version,
                vector_blob = excluded.vector_blob
            """,
            (
                resource_id,
                resource_type,
                fingerprint,
                fingerprint,
                model_version,
                vector.tobytes(),
            ),
        )
        written += 1

    for row in entry_rows:
        _upsert(row["public_id"], "entry", _build_entry_text(row), row["fingerprint"])

    for row in event_rows:
        _upsert(row["public_id"], "event", _build_event_text(row), row["fingerprint"])

    conn.executemany(
        """
        INSERT INTO metadata(key, value) VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        [
            ("embedding_model", manifest.model_name),
            ("embedding_model_version", model_version),
            ("embedding_vector_dim", str(manifest.vector_dim)),
        ],
    )

    return written


def get_vector(conn: sqlite3.Connection, resource_id: str, resource_type: str) -> np.ndarray | None:
    """Load a stored embedding vector from the database."""
    row = conn.execute(
        "SELECT vector_blob FROM embeddings WHERE resource_id = ? AND resource_type = ?",
        (resource_id, resource_type),
    ).fetchone()
    if row is None:
        return None
    return np.frombuffer(row[0], dtype=np.float32).copy()


def embed_query(root: Path, text: str) -> np.ndarray:
    """Embed a query string using the vendored model."""
    model = load_vendored_model(root)
    return _normalize_vector(model.encode([text])[0].astype(np.float32))


def validate_embeddings_consistency(root: Path, conn: sqlite3.Connection) -> list[ValidationIssue]:
    """Return validation issues for embedding drift or missing schema."""
    if not _table_exists(conn, "embeddings"):
        return [
            ValidationIssue(
                code="ERR_MISSING_TABLE",
                message="Required table `embeddings` does not exist.",
                details={"table": "embeddings"},
            )
        ]

    issues: list[ValidationIssue] = []
    manifest = load_manifest(root)
    model_version = manifest.model_version

    stale_entries = conn.execute(
        """
        SELECT COUNT(*)
        FROM entries e
        LEFT JOIN embeddings emb
            ON emb.resource_id = e.public_id
           AND emb.resource_type = 'entry'
        WHERE emb.resource_id IS NULL
           OR emb.content_fingerprint != e.fingerprint
           OR emb.model_version != ?
        """,
        (model_version,),
    ).fetchone()[0]
    if stale_entries:
        issues.append(
            ValidationIssue(
                code="ERR_EMBEDDING_DRIFT_ENTRIES",
                message=(
                    f"{stale_entries} entry embedding rows are missing or stale. "
                    "Run `cwmem build` to resync."
                ),
                details={"stale_entries": stale_entries, "model_version": model_version},
            )
        )

    stale_events = conn.execute(
        """
        SELECT COUNT(*)
        FROM events e
        LEFT JOIN embeddings emb
            ON emb.resource_id = e.public_id
           AND emb.resource_type = 'event'
        WHERE emb.resource_id IS NULL
           OR emb.content_fingerprint != e.fingerprint
           OR emb.model_version != ?
        """,
        (model_version,),
    ).fetchone()[0]
    if stale_events:
        issues.append(
            ValidationIssue(
                code="ERR_EMBEDDING_DRIFT_EVENTS",
                message=(
                    f"{stale_events} event embedding rows are missing or stale. "
                    "Run `cwmem build` to resync."
                ),
                details={"stale_events": stale_events, "model_version": model_version},
            )
        )

    orphan_rows = conn.execute(
        """
        SELECT COUNT(*)
        FROM embeddings emb
        LEFT JOIN entries e
            ON emb.resource_type = 'entry'
           AND e.public_id = emb.resource_id
        LEFT JOIN events ev
            ON emb.resource_type = 'event'
           AND ev.public_id = emb.resource_id
        WHERE (emb.resource_type = 'entry' AND e.public_id IS NULL)
           OR (emb.resource_type = 'event' AND ev.public_id IS NULL)
        """
    ).fetchone()[0]
    if orphan_rows:
        issues.append(
            ValidationIssue(
                code="ERR_EMBEDDING_ORPHAN_ROWS",
                message=(
                    f"{orphan_rows} embedding rows do not map to a live entry or event. "
                    "Run `cwmem build` to resync."
                ),
                details={"orphan_rows": orphan_rows},
            )
        )

    return issues


def _copy_tree_contents(source: Path, target: Path) -> None:
    for child in source.iterdir():
        destination = target / child.name
        if child.is_dir():
            shutil.copytree(child, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(child, destination)


def _delete_orphan_rows(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        DELETE FROM embeddings
        WHERE resource_type = 'entry'
          AND NOT EXISTS (
              SELECT 1 FROM entries e WHERE e.public_id = embeddings.resource_id
          )
        """
    )
    conn.execute(
        """
        DELETE FROM embeddings
        WHERE resource_type = 'event'
          AND NOT EXISTS (
              SELECT 1 FROM events e WHERE e.public_id = embeddings.resource_id
          )
        """
    )


def _model_bundle_complete(model_root: Path) -> bool:
    return (model_root / _MANIFEST_NAME).is_file() and _model_payload_complete(model_root / "model")


def _model_payload_complete(model_dir: Path) -> bool:
    return model_dir.is_dir() and all(
        (model_dir / name).is_file() for name in _REQUIRED_MODEL_FILES
    )


def _normalize_vector(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm == 0.0:
        return vector
    return vector / norm


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None
