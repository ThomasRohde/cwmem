from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path

from tests.phase2_helpers import extract_entries, init_repo, run_ok
from tests.phase7_helpers import hold_sidecar_lock, run_phase7_any, skip_if_locking_unavailable


def _lock_owner_metadata() -> dict[str, object]:
    return {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "command": "phase7.lock-holder",
        "request_id": "req_phase7_lock_holder",
        "acquired_at": datetime.now(UTC).isoformat(),
    }


def test_mutating_commands_fail_with_lock_held_and_owner_metadata(
    run_cli, tmp_path: Path
) -> None:
    skip_if_locking_unavailable(run_cli, tmp_path)
    init_repo(run_cli, tmp_path)

    metadata = _lock_owner_metadata()
    with hold_sidecar_lock(tmp_path, metadata):
        completed, payload = run_phase7_any(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Lock contention target",
            "--type",
            "note",
            "This mutation should be blocked by the sidecar lock.",
        )

    assert payload["command"] == "memory.add"
    assert completed.returncode == 40, (
        "Lock contention should map to the conflict exit code.\n"
        f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    )
    assert payload["ok"] is False

    error = next(error for error in payload["errors"] if error["code"] == "ERR_LOCK_HELD")
    assert error["retryable"] is True

    serialized = json.dumps(error, sort_keys=True)
    assert str(metadata["pid"]) in serialized
    assert str(metadata["command"]) in serialized

    list_payload = run_ok(run_cli, tmp_path, "list")
    assert extract_entries(list_payload) == []


def test_read_commands_remain_available_while_write_lock_is_held(
    run_cli, tmp_path: Path
) -> None:
    skip_if_locking_unavailable(run_cli, tmp_path)
    init_repo(run_cli, tmp_path)

    created_entry = run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Read while locked",
        "--type",
        "note",
        "Reads should remain parallel-safe while a writer holds the lock.",
    )

    with hold_sidecar_lock(tmp_path, _lock_owner_metadata()):
        list_payload = run_ok(run_cli, tmp_path, "list")

    listed_entries = extract_entries(list_payload)
    assert [entry["public_id"] for entry in listed_entries] == [
        created_entry["result"]["entry"]["public_id"]
    ]
