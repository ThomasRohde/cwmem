from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.helpers import assert_required_envelope_keys


def parse_envelope_any_exit(stdout: str, stderr: str) -> dict[str, Any]:
    trimmed = stdout.strip()
    assert trimmed, f"Expected a JSON envelope on stdout. STDERR:\n{stderr}"

    try:
        payload = json.loads(trimmed)
    except json.JSONDecodeError as exc:  # pragma: no cover - exercised only on contract failure
        raise AssertionError(
            "stdout must contain exactly one JSON envelope.\n"
            f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        ) from exc

    assert isinstance(payload, dict), f"Envelope must decode to an object, got: {type(payload)!r}"
    assert_required_envelope_keys(payload)
    return payload


def _maybe_skip_not_implemented(completed, payload: dict[str, Any], args: tuple[str, ...]) -> None:
    errors = payload.get("errors", [])
    error_codes = {error.get("code") for error in errors if isinstance(error, dict)}
    is_placeholder_response = (
        completed.returncode in (10, 90)
        and payload.get("ok") is False
        and error_codes == {"ERR_NOT_IMPLEMENTED"}
    )
    if is_placeholder_response:
        pytest.skip(
            "Phase 2 CRUD/event CLI is still scaffold-only. "
            "Final integration verification belongs to e2-reconcile-verify.\n"
            f"Skipped while running: cwmem {' '.join(args)}"
        )


def run_ok(run_cli, tmp_path: Path, *args: str) -> dict[str, Any]:
    completed = run_cli(tmp_path, *args)
    payload = parse_envelope_any_exit(completed.stdout, completed.stderr)
    _maybe_skip_not_implemented(completed, payload, args)
    assert completed.returncode == 0, (
        f"Expected success exit code for `cwmem {' '.join(args)}`.\n"
        f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    )
    assert payload["ok"] is True, payload
    return payload


def run_any(run_cli, tmp_path: Path, *args: str):
    completed = run_cli(tmp_path, *args)
    payload = parse_envelope_any_exit(completed.stdout, completed.stderr)
    _maybe_skip_not_implemented(completed, payload, args)
    return completed, payload


def init_repo(run_cli, tmp_path: Path) -> dict[str, Any]:
    payload = run_ok(run_cli, tmp_path, "init")
    assert payload["command"] == "system.init"
    return payload


def extract_entry(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    assert isinstance(result, dict), f"Expected object result, got: {type(result)!r}"

    if "entry" in result:
        entry = result["entry"]
        assert isinstance(entry, dict), f"Expected `entry` to be an object, got: {type(entry)!r}"
        return entry

    if {"public_id", "fingerprint"}.issubset(result):
        return result

    raise AssertionError(f"Could not find entry object in result payload: {result!r}")


def extract_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload["result"]
    assert isinstance(result, dict), f"Expected object result, got: {type(result)!r}"

    for key in ("entries", "items", "results"):
        value = result.get(key)
        if isinstance(value, list):
            assert all(isinstance(item, dict) for item in value), value
            return value

    raise AssertionError(f"Could not find entry list in result payload: {result!r}")


def extract_event(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    assert isinstance(result, dict), f"Expected object result, got: {type(result)!r}"

    if "event" in result:
        event = result["event"]
        assert isinstance(event, dict), f"Expected `event` to be an object, got: {type(event)!r}"
        return event

    if {"public_id", "event_type"}.issubset(result):
        return result

    raise AssertionError(f"Could not find event object in result payload: {result!r}")


def extract_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload["result"]
    assert isinstance(result, dict), f"Expected object result, got: {type(result)!r}"

    for key in ("events", "items", "results"):
        value = result.get(key)
        if isinstance(value, list):
            assert all(isinstance(item, dict) for item in value), value
            return value

    raise AssertionError(f"Could not find event list in result payload: {result!r}")

