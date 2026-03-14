from __future__ import annotations

import json
from pathlib import Path

from tests.phase2_helpers import extract_entry, init_repo, run_any, run_ok
from tests.phase3_helpers import (
    clear_fts_table,
    execute_sql,
    select_count,
    stats_count,
    table_exists,
)


def _assert_validate_problem(completed, payload: dict[str, object]) -> str:
    assert payload["command"] == "system.validate"

    result = payload.get("result")
    is_result_problem = isinstance(result, dict) and result.get("ok") is False
    assert payload["ok"] is False or is_result_problem, payload

    if payload["ok"] is False:
        assert completed.returncode == 10, (
            "Validation envelopes should use the validation exit code "
            "when the command itself fails.\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    else:
        assert completed.returncode == 0, (
            "Structured validation results should still exit successfully.\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
        issues = result.get("issues")
        assert isinstance(issues, list) and issues, result

    return json.dumps(payload, sort_keys=True).lower()


def test_stats_reports_primary_and_fts_counts(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    entry = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Stats baseline entry",
            "--type",
            "decision",
            "--author",
            "alice",
            "Stats baseline content for primary rows.",
        )
    )
    run_ok(
        run_cli,
        tmp_path,
        "event-add",
        "--event-type",
        "decision.recorded",
        "--summary",
        "Stats baseline event",
        "--body",
        "Stats baseline content for event rows.",
        "--actor",
        "alice",
        "--resource",
        entry["public_id"],
    )
    run_ok(run_cli, tmp_path, "build")

    stats_payload = run_ok(run_cli, tmp_path, "stats")
    assert stats_payload["command"] == "system.stats"

    result = stats_payload["result"]
    assert isinstance(result, dict), result
    assert stats_count(result, "entries", "entries_count") == select_count(tmp_path, "entries")
    assert stats_count(result, "events", "events_count") == select_count(tmp_path, "events")
    assert stats_count(result, "entries_fts", "entries_fts_count") == select_count(
        tmp_path, "entries_fts"
    )
    assert stats_count(result, "events_fts", "events_fts_count") == select_count(
        tmp_path, "events_fts"
    )
    assert stats_count(result, "embeddings", "embeddings_count") == (
        select_count(tmp_path, "entries") + select_count(tmp_path, "events")
    )
    assert result.get("embedding_model") == "minishlab/potion-base-8M"


def test_validate_succeeds_when_primary_and_fts_counts_align(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Validation baseline",
        "--type",
        "decision",
        "--author",
        "alice",
        "Validation baseline content for aligned indexes.",
    )
    run_ok(run_cli, tmp_path, "build")

    validate_payload = run_ok(run_cli, tmp_path, "validate")
    assert validate_payload["command"] == "system.validate"
    assert validate_payload["ok"] is True

    result = validate_payload["result"]
    assert isinstance(result, dict), result
    if "ok" in result:
        assert result["ok"] is True
    for key in ("valid", "aligned", "healthy"):
        if key in result:
            assert result[key] is True
    issues = result.get("issues")
    if issues is not None:
        assert issues == []


def test_validate_reports_fts_drift_after_manual_index_clear(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Drift target",
        "--type",
        "decision",
        "--author",
        "alice",
        "Validation drift baseline content.",
    )
    run_ok(run_cli, tmp_path, "build")
    assert select_count(tmp_path, "entries") >= 1
    assert select_count(tmp_path, "entries_fts") >= 1

    clear_fts_table(tmp_path, "entries_fts")
    assert select_count(tmp_path, "entries_fts") == 0

    completed, payload = run_any(run_cli, tmp_path, "validate")
    serialized = _assert_validate_problem(completed, payload)
    assert "fts" in serialized
    assert "entries_fts" in serialized or "entries" in serialized
    assert "drift" in serialized or "mismatch" in serialized or "count" in serialized


def test_validate_reports_problem_when_required_fts_table_is_removed(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)

    run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Missing table target",
        "--type",
        "decision",
        "--author",
        "alice",
        "Validation missing-table baseline content.",
    )
    run_ok(run_cli, tmp_path, "build")

    execute_sql(tmp_path, 'DROP TABLE "entries_fts"')
    assert not table_exists(tmp_path, "entries_fts")

    completed, payload = run_any(run_cli, tmp_path, "validate")
    serialized = _assert_validate_problem(completed, payload)
    assert "entries_fts" in serialized
    assert "missing" in serialized or "required" in serialized or "schema" in serialized or (
        "drift" in serialized or "mismatch" in serialized or "count" in serialized
    )
