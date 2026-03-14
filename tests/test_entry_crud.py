from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.phase2_helpers import (
    extract_entries,
    extract_entry,
    init_repo,
    parse_envelope_any_exit,
    run_any,
    run_ok,
)


def test_add_get_list_update_round_trip_and_fingerprint_change(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)

    add_payload = run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Capability model alignment",
        "--type",
        "decision",
        "--author",
        "thomas",
        "--tags",
        "capability-model",
        "--tags",
        "governance",
        "We aligned the EA capability model with the BCM baseline.",
    )
    assert add_payload["command"] == "memory.add"

    created_entry = extract_entry(add_payload)
    assert created_entry["public_id"] == "mem-000001"
    assert created_entry["title"] == "Capability model alignment"
    assert created_entry["type"] == "decision"
    assert created_entry["author"] == "thomas"
    assert created_entry["fingerprint"].startswith("sha256:")
    assert set(created_entry.get("tags", [])) == {"capability-model", "governance"}

    get_payload = run_ok(run_cli, tmp_path, "get", "mem-000001")
    assert get_payload["command"] == "memory.get"
    retrieved_entry = extract_entry(get_payload)
    assert retrieved_entry["public_id"] == created_entry["public_id"]
    assert retrieved_entry["fingerprint"] == created_entry["fingerprint"]
    assert retrieved_entry["title"] == created_entry["title"]

    list_payload = run_ok(run_cli, tmp_path, "list")
    assert list_payload["command"] == "memory.list"
    listed_entries = extract_entries(list_payload)
    assert [entry["public_id"] for entry in listed_entries] == ["mem-000001"]

    update_payload = run_ok(
        run_cli,
        tmp_path,
        "update",
        "mem-000001",
        "--expected-fingerprint",
        created_entry["fingerprint"],
        "--title",
        "Capability model alignment v2",
    )
    assert update_payload["command"] == "memory.update"
    updated_entry = extract_entry(update_payload)
    assert updated_entry["public_id"] == "mem-000001"
    assert updated_entry["title"] == "Capability model alignment v2"
    assert updated_entry["fingerprint"].startswith("sha256:")
    assert updated_entry["fingerprint"] != created_entry["fingerprint"]

    refreshed_payload = run_ok(run_cli, tmp_path, "get", "mem-000001")
    refreshed_entry = extract_entry(refreshed_payload)
    assert refreshed_entry["public_id"] == "mem-000001"
    assert refreshed_entry["title"] == "Capability model alignment v2"
    assert refreshed_entry["fingerprint"] == updated_entry["fingerprint"]


def test_list_order_is_deterministic_by_public_id(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "First entry",
        "--type",
        "decision",
        "--author",
        "thomas",
        "First body.",
    )
    run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Second entry",
        "--type",
        "finding",
        "--author",
        "thomas",
        "Second body.",
    )

    list_payload = run_ok(run_cli, tmp_path, "list")
    listed_entries = extract_entries(list_payload)
    public_ids = [entry["public_id"] for entry in listed_entries]
    assert public_ids[:2] == ["mem-000001", "mem-000002"]
    assert public_ids == sorted(public_ids)


def test_update_rejects_stale_fingerprint(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    add_payload = run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Concurrency-safe update target",
        "--type",
        "decision",
        "--author",
        "thomas",
        "Original body.",
    )
    entry = extract_entry(add_payload)
    stale_fingerprint = entry["fingerprint"]

    successful_update = run_ok(
        run_cli,
        tmp_path,
        "update",
        entry["public_id"],
        "--expected-fingerprint",
        stale_fingerprint,
        "--title",
        "Fresh title",
    )
    assert extract_entry(successful_update)["fingerprint"] != stale_fingerprint

    completed, payload = run_any(
        run_cli,
        tmp_path,
        "update",
        entry["public_id"],
        "--expected-fingerprint",
        stale_fingerprint,
        "--title",
        "Stale write should fail",
    )
    assert completed.returncode == 40, (
        "Stale fingerprint updates should map to the conflict exit code.\n"
        f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    )
    assert payload["ok"] is False
    assert payload["command"] == "memory.update"

    error_codes = [error["code"] for error in payload["errors"]]
    assert any(code.startswith("ERR_CONFLICT_") for code in error_codes), error_codes

    serialized_errors = json.dumps(payload["errors"], sort_keys=True).lower()
    assert "fingerprint" in serialized_errors or "stale" in serialized_errors


def test_add_accepts_plain_text_body_from_stdin(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)
    body = "Body from stdin.\nSecond line.\n"

    completed = run_cli(
        tmp_path,
        "add",
        "--title",
        "stdin body",
        "--type",
        "note",
        "--body-from-stdin",
        input_text=body,
    )
    payload = parse_envelope_any_exit(completed.stdout, completed.stderr)

    assert completed.returncode == 0, completed
    assert payload["ok"] is True, payload
    created_entry = extract_entry(payload)
    assert created_entry["title"] == "stdin body"
    assert created_entry["body"] == body


def test_add_rejects_body_from_stdin_when_inline_body_is_also_supplied(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)

    completed = run_cli(
        tmp_path,
        "add",
        "--title",
        "stdin conflict",
        "--body-from-stdin",
        "Inline body",
        input_text="Piped body",
    )
    payload = parse_envelope_any_exit(completed.stdout, completed.stderr)

    assert completed.returncode == 10, completed
    assert payload["ok"] is False, payload
    assert payload["command"] == "memory.add"
    assert [error["code"] for error in payload["errors"]] == ["ERR_VALIDATION_INPUT"]

    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "body-from-stdin" in serialized
    assert "not both" in serialized


def test_add_rejects_binary_stdin_with_validation_error(
    run_cli, cli_env: dict[str, str], tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)

    completed = subprocess.run(
        [sys.executable, "-m", "cwmem", "add", "--title", "binary stdin", "--body-from-stdin"],
        cwd=tmp_path,
        env=cli_env,
        capture_output=True,
        input=bytes(range(256)),
        text=False,
        check=False,
        timeout=30,
    )
    stdout = completed.stdout.decode("utf-8")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    payload = parse_envelope_any_exit(stdout, stderr)

    assert completed.returncode == 10, completed
    assert payload["ok"] is False, payload
    assert payload["command"] == "memory.add"
    assert [error["code"] for error in payload["errors"]] == ["ERR_VALIDATION_INPUT"]

    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "stdin" in serialized
    assert "utf-8" in serialized or "text" in serialized
    assert "err_internal_unhandled" not in serialized

