from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from tests.phase2_helpers import parse_envelope_any_exit, run_ok

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCKING_MODULE_PATH = REPO_ROOT / "src" / "cwmem" / "core" / "locking.py"


def run_phase7_any(
    run_cli,
    tmp_path: Path,
    *args: str,
    missing_option_names: tuple[str, ...] = (),
):
    completed = run_cli(tmp_path, *args)
    payload = parse_envelope_any_exit(completed.stdout, completed.stderr)
    _maybe_skip_phase7_unavailable(completed, payload, args, missing_option_names)
    return completed, payload


def run_phase7_ok(
    run_cli,
    tmp_path: Path,
    *args: str,
    missing_option_names: tuple[str, ...] = (),
) -> dict[str, Any]:
    completed, payload = run_phase7_any(
        run_cli,
        tmp_path,
        *args,
        missing_option_names=missing_option_names,
    )
    assert completed.returncode == 0, (
        f"Expected success exit code for `cwmem {' '.join(args)}`.\n"
        f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    )
    assert payload["ok"] is True, payload
    return payload


def skip_if_locking_unavailable(run_cli, tmp_path: Path) -> None:
    if LOCKING_MODULE_PATH.is_file():
        return

    guide_payload = run_ok(run_cli, tmp_path, "guide")
    result = guide_payload["result"]
    assert isinstance(result, dict), result

    policy = result.get("concurrency_policy", {})
    serialized = json.dumps(policy, sort_keys=True).lower()
    if "planned" in serialized and ("not enforced" in serialized or "later phase" in serialized):
        pytest.skip(
            "Phase 7 locking is not landed yet. These tests define the lock contract "
            "and should pass once e7-safety-code exists."
        )


@contextmanager
def hold_sidecar_lock(repo_root: Path, metadata: dict[str, Any]):
    lock_path = repo_root / ".cwmem" / "memory.sqlite.lock"
    metadata_path = repo_root / ".cwmem" / "memory.sqlite.lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("w+", encoding="utf-8") as handle:
        handle.write(json.dumps(metadata, sort_keys=True))
        handle.flush()
        os.fsync(handle.fileno())
        with metadata_path.open("w", encoding="utf-8") as metadata_handle:
            metadata_handle.write(json.dumps(metadata, sort_keys=True))
            metadata_handle.flush()
            os.fsync(metadata_handle.fileno())
        lock_size = max(1, handle.tell())
        _acquire_file_lock(handle, lock_size)
        try:
            yield lock_path
        finally:
            _release_file_lock(handle, lock_size)
            metadata_path.unlink(missing_ok=True)


def _maybe_skip_phase7_unavailable(
    completed,
    payload: dict[str, Any],
    args: tuple[str, ...],
    missing_option_names: tuple[str, ...],
) -> None:
    errors = payload.get("errors", [])
    error_codes = {error.get("code") for error in errors if isinstance(error, dict)}
    is_placeholder_response = (
        completed.returncode in (10, 90)
        and payload.get("ok") is False
        and error_codes == {"ERR_NOT_IMPLEMENTED"}
    )
    if is_placeholder_response:
        pytest.skip(
            "Phase 7 safety implementation is not landed yet. "
            "These tests define the CLI contract and should pass once e7-safety-code "
            "exists.\n"
            f"Skipped while running: cwmem {' '.join(args)}"
        )

    if not missing_option_names:
        return

    is_missing_option_response = (
        completed.returncode == 10
        and payload.get("ok") is False
        and error_codes == {"ERR_VALIDATION_INPUT"}
    )
    if not is_missing_option_response:
        return

    serialized = json.dumps(payload, sort_keys=True).lower()
    exception_types = {
        str(error.get("details", {}).get("exception_type", "")).lower()
        for error in errors
        if isinstance(error, dict)
    }
    is_missing_option = "nosuchoption" in exception_types or "no such option" in serialized
    mentions_requested_option = any(option.lower() in serialized for option in missing_option_names)
    if is_missing_option and mentions_requested_option:
        option_list = ", ".join(missing_option_names)
        pytest.skip(
            "Phase 7 safety options are not wired yet. "
            "These tests define the CLI contract and should pass once e7-safety-code "
            f"exists.\nMissing option(s): {option_list}\n"
            f"Skipped while running: cwmem {' '.join(args)}"
        )


if os.name == "nt":
    import msvcrt

    def _acquire_file_lock(handle, lock_size: int) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, lock_size)

    def _release_file_lock(handle, lock_size: int) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, lock_size)

else:
    import fcntl

    def _acquire_file_lock(handle, lock_size: int) -> None:
        _ = lock_size
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release_file_lock(handle, lock_size: int) -> None:
        _ = lock_size
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
