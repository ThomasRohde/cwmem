from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import orjson

from cwmem.core import store as _store
from cwmem.core.locking import acquire_lock
from cwmem.output.envelope import current_request_id
from cwmem.output.json import to_json_bytes


def stable_hash(value: Any) -> str:
    return f"sha256:{hashlib.sha256(to_json_bytes(value)).hexdigest()}"


def serialize_payload(value: Any) -> Any:
    return orjson.loads(to_json_bytes(value))


def impacted_resource_ids(value: Any) -> list[str]:
    found: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            public_id = node.get("public_id")
            if isinstance(public_id, str):
                found.add(public_id)
            for child in node.values():
                visit(child)
            return
        if isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return sorted(found)


@contextmanager
def dry_run_root(root: Path):
    with tempfile.TemporaryDirectory(prefix="cwmem-dry-run-") as temp_dir:
        preview_root = Path(temp_dir)
        source_db = _store.database_path(root)
        if source_db.exists():
            target_db = _store.database_path(preview_root)
            target_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_db, target_db)
        yield preview_root


def execute_mutation(
    *,
    root: Path,
    command_id: str,
    request_payload: Any,
    apply_handler: Callable[[Path], Any],
    summary_builder: Callable[[dict[str, Any]], dict[str, int]],
    dry_run: bool = False,
    idempotency_key: str | None = None,
    wait_lock: float = 0.0,
    preview_handler: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    request_hash = stable_hash(request_payload)
    with acquire_lock(
        root,
        command=command_id,
        wait_seconds=wait_lock,
        request_id=current_request_id(),
    ):
        if not dry_run and idempotency_key:
            replay = _store.replay_idempotent_success(
                root,
                command_id=command_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            if replay is not None:
                return replay

        if dry_run:
            if preview_handler is None:
                with dry_run_root(root) as preview_root:
                    preview_payload = serialize_payload(apply_handler(preview_root))
            else:
                preview_payload = serialize_payload(preview_handler())
            preview_result = (
                dict(preview_payload)
                if isinstance(preview_payload, dict)
                else {"preview": preview_payload}
            )
            preview_result["dry_run"] = True
            preview_result["applied"] = False
            preview_result["summary"] = summary_builder(
                preview_payload if isinstance(preview_payload, dict) else {}
            )
            preview_result["impacted_resources"] = impacted_resource_ids(preview_payload)
            return preview_result

        result_payload = serialize_payload(apply_handler(root))
        if idempotency_key:
            _store.record_idempotent_success(
                root,
                command_id=command_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                request_id=current_request_id() or "req_manual",
                resource_ids=impacted_resource_ids(result_payload),
                response=(
                    result_payload
                    if isinstance(result_payload, dict)
                    else {"result": result_payload}
                ),
            )
        if isinstance(result_payload, dict):
            return result_payload
        return {"result": result_payload}
