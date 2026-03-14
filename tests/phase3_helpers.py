from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def memory_db_path(repo_root: Path) -> Path:
    return repo_root / ".cwmem" / "memory.sqlite"


def execute_sql(repo_root: Path, sql: str, params: tuple[Any, ...] = ()) -> None:
    with sqlite3.connect(memory_db_path(repo_root)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(sql, params)
        conn.commit()


def select_count(repo_root: Path, table_name: str) -> int:
    quoted = _quote_identifier(table_name)
    with sqlite3.connect(memory_db_path(repo_root)) as conn:
        row = conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()
    assert row is not None
    return int(row[0])


def table_exists(repo_root: Path, table_name: str) -> bool:
    with sqlite3.connect(memory_db_path(repo_root)) as conn:
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


def clear_fts_table(repo_root: Path, table_name: str) -> None:
    quoted = _quote_identifier(table_name)
    with sqlite3.connect(memory_db_path(repo_root)) as conn:
        try:
            conn.execute(f"DELETE FROM {quoted}")
        except sqlite3.DatabaseError:
            conn.execute(f"INSERT INTO {quoted}({quoted}) VALUES ('delete-all')")
        conn.commit()


def extract_search_hits(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload["result"]

    if isinstance(result, list):
        assert all(isinstance(item, dict) for item in result), result
        return result

    assert isinstance(result, dict), f"Expected object result, got: {type(result)!r}"
    for key in ("hits", "results", "items"):
        value = result.get(key)
        if isinstance(value, list):
            assert all(isinstance(item, dict) for item in value), value
            return value

    raise AssertionError(f"Could not find search hit list in result payload: {result!r}")


def find_search_hit(hits: list[dict[str, Any]], resource_id: str) -> dict[str, Any] | None:
    for hit in hits:
        if search_hit_resource_id(hit) == resource_id:
            return hit
    return None


def search_hit_resource_id(hit: dict[str, Any]) -> str:
    for key in ("resource_id", "public_id", "id"):
        value = hit.get(key)
        if isinstance(value, str):
            return value

    resource = hit.get("resource")
    if isinstance(resource, dict):
        for key in ("resource_id", "public_id", "id"):
            value = resource.get(key)
            if isinstance(value, str):
                return value

    raise AssertionError(f"Could not find resource identifier in search hit: {hit!r}")


def stats_count(result: dict[str, Any], *keys: str) -> int:
    containers: list[dict[str, Any]] = [result]
    for container_name in ("counts", "tables", "fts", "indexes"):
        container = result.get(container_name)
        if isinstance(container, dict):
            containers.append(container)

    for container in containers:
        candidate_keys = list(keys)
        for key in keys:
            if key.endswith("_fts_count"):
                candidate_keys.append(key.removesuffix("_count"))
                candidate_keys.append(key.removesuffix("_fts_count"))
            elif key.endswith("_fts"):
                candidate_keys.append(key.removesuffix("_fts"))
            elif key.endswith("_count"):
                candidate_keys.append(key.removesuffix("_count"))

        for key in candidate_keys:
            value = container.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, dict):
                for nested_key in ("count", "row_count", "rows", "value"):
                    nested = value.get(nested_key)
                    if isinstance(nested, int):
                        return nested

    raise AssertionError(f"Could not find stats count for keys {keys!r} in result: {result!r}")


def _quote_identifier(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum():
        raise ValueError(f"Unsafe SQLite identifier: {identifier!r}")
    return f'"{identifier}"'
