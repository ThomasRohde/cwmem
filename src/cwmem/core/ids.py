from __future__ import annotations

import secrets
import sqlite3
import time

_CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

_PUBLIC_ID_CONFIG: dict[str, tuple[str, str]] = {
    "mem": ("next_mem_id", "mem"),
    "evt": ("next_evt_id", "evt"),
}


def _encode_crockford(value: int, length: int) -> str:
    encoded = ["0"] * length
    for index in range(length - 1, -1, -1):
        encoded[index] = _CROCKFORD_BASE32[value & 31]
        value >>= 5
    return "".join(encoded)


def generate_internal_id() -> str:
    timestamp_ms = int(time.time() * 1000)
    randomness = secrets.randbits(80)
    return f"{_encode_crockford(timestamp_ms, 10)}{_encode_crockford(randomness, 16)}"


def next_public_id(conn: sqlite3.Connection, kind: str) -> str:
    try:
        key, prefix = _PUBLIC_ID_CONFIG[kind]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported public id kind: {kind}") from exc

    row = conn.execute(
        """
        UPDATE metadata
        SET value = CAST(value AS INTEGER) + 1
        WHERE key = ?
        RETURNING value
        """,
        (key,),
    ).fetchone()
    if row is None:  # pragma: no cover - defensive
        raise ValueError(f"Metadata counter missing for kind: {kind}")
    next_number = int(row[0]) - 1
    return f"{prefix}-{next_number:06d}"
