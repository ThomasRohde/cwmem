from __future__ import annotations

import json
from pathlib import Path

from tests.phase2_helpers import extract_entries, extract_entry, init_repo, run_ok
from tests.phase3_helpers import select_count
from tests.phase7_helpers import run_phase7_any, run_phase7_ok

IDEMPOTENCY_KEY = "phase7-idempotency-demo"


def test_add_retries_with_same_idempotency_key_replay_original_entry(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)

    first_payload = run_phase7_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Idempotent write",
        "--type",
        "note",
        "--idempotency-key",
        IDEMPOTENCY_KEY,
        "This write should persist once.",
        missing_option_names=("--idempotency-key",),
    )
    first_entry = extract_entry(first_payload)

    second_payload = run_phase7_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Idempotent write",
        "--type",
        "note",
        "--idempotency-key",
        IDEMPOTENCY_KEY,
        "This write should persist once.",
        missing_option_names=("--idempotency-key",),
    )
    second_entry = extract_entry(second_payload)

    assert second_entry["public_id"] == first_entry["public_id"]
    assert second_entry["fingerprint"] == first_entry["fingerprint"]
    assert select_count(tmp_path, "entries") == 1
    assert select_count(tmp_path, "events") == 1

    list_payload = run_ok(run_cli, tmp_path, "list")
    listed_entries = extract_entries(list_payload)
    assert [entry["public_id"] for entry in listed_entries] == [first_entry["public_id"]]


def test_idempotency_key_rejects_different_request_payloads(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)

    run_phase7_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Original idempotent write",
        "--type",
        "note",
        "--idempotency-key",
        IDEMPOTENCY_KEY,
        "Original request body.",
        missing_option_names=("--idempotency-key",),
    )
    before_counts = {
        "entries": select_count(tmp_path, "entries"),
        "events": select_count(tmp_path, "events"),
    }

    completed, payload = run_phase7_any(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Conflicting idempotent write",
        "--type",
        "note",
        "--idempotency-key",
        IDEMPOTENCY_KEY,
        "Different request body should not replay successfully.",
        missing_option_names=("--idempotency-key",),
    )

    assert payload["command"] == "memory.add"
    result = payload.get("result")
    is_result_problem = isinstance(result, dict) and result.get("ok") is False
    assert payload["ok"] is False or is_result_problem, payload

    if payload["ok"] is False:
        assert completed.returncode in {10, 40}, (
            "Idempotency conflicts should use validation or conflict exit codes.\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    else:
        assert completed.returncode == 0, completed

    assert select_count(tmp_path, "entries") == before_counts["entries"]
    assert select_count(tmp_path, "events") == before_counts["events"]

    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "idempot" in serialized or "hash" in serialized, payload
    assert any(
        token in serialized for token in ("mismatch", "different", "conflict", "request")
    ), payload
