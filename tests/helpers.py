from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

REQUIRED_ENVELOPE_KEYS = {
    "schema_version",
    "request_id",
    "ok",
    "command",
    "result",
    "warnings",
    "errors",
    "metrics",
}


def parse_envelope(stdout: str, stderr: str, returncode: int) -> dict[str, Any]:
    assert returncode == 0, (
        f"Command failed with exit code {returncode}\n"
        f"STDOUT:\n{stdout}\n"
        f"STDERR:\n{stderr}"
    )
    trimmed = stdout.strip()
    assert trimmed, f"Expected JSON envelope on stdout, got empty stdout. STDERR:\n{stderr}"

    try:
        payload = json.loads(trimmed)
    except json.JSONDecodeError as exc:  # pragma: no cover - exercised only on contract failure
        raise AssertionError(
            f"stdout must contain exactly one JSON envelope.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        ) from exc

    assert isinstance(payload, dict), f"Envelope must decode to an object, got: {type(payload)!r}"
    return payload


def assert_required_envelope_keys(payload: dict[str, Any]) -> None:
    missing = REQUIRED_ENVELOPE_KEYS.difference(payload)
    assert not missing, f"Envelope missing required keys: {sorted(missing)}"
    assert isinstance(payload["warnings"], list), "`warnings` must be a list"
    assert isinstance(payload["errors"], list), "`errors` must be a list"
    assert isinstance(payload["metrics"], dict), "`metrics` must be an object"


def flatten_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for nested in value.values():
            yield from flatten_strings(nested)
        return
    if isinstance(value, list):
        for nested in value:
            yield from flatten_strings(nested)

