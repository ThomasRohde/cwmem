from __future__ import annotations

from pathlib import Path

from tests.phase2_helpers import extract_entry, init_repo, run_ok
from tests.phase3_helpers import (
    execute_sql,
    extract_search_hits,
    find_search_hit,
    search_hit_resource_id,
    select_count,
    table_exists,
)


def test_search_finds_new_entries_without_manual_rebuild(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    add_payload = run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Immediate FTS visibility",
        "--type",
        "decision",
        "--author",
        "alice",
        "Instant lexical marker proves transactional indexing is active.",
    )
    entry = extract_entry(add_payload)

    search_payload = run_ok(
        run_cli,
        tmp_path,
        "search",
        "instant lexical marker",
        "--lexical-only",
    )
    assert search_payload["command"] == "memory.search"

    hits = extract_search_hits(search_payload)
    hit = find_search_hit(hits, entry["public_id"])
    assert hit is not None, hits
    match_modes = hit.get("match_modes")
    assert isinstance(match_modes, list), hit
    assert "lexical" in match_modes

    explanation = hit.get("explanation")
    assert isinstance(explanation, dict), hit
    matched_fields = explanation.get("matched_fields")
    assert isinstance(matched_fields, list), explanation
    assert "body" in matched_fields or "title" in matched_fields


def test_search_refreshes_entry_index_after_update(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    add_payload = run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Refresh target",
        "--type",
        "decision",
        "--author",
        "alice",
        "Original body without the later update token.",
    )
    entry = extract_entry(add_payload)

    before_update_payload = run_ok(
        run_cli,
        tmp_path,
        "search",
        "fresh-update-token",
        "--lexical-only",
    )
    before_update_ids = {
        search_hit_resource_id(hit) for hit in extract_search_hits(before_update_payload)
    }
    assert entry["public_id"] not in before_update_ids

    update_payload = run_ok(
        run_cli,
        tmp_path,
        "update",
        entry["public_id"],
        "--expected-fingerprint",
        entry["fingerprint"],
        "--body",
        "Updated body carries the fresh-update-token for lexical refresh verification.",
    )
    updated_entry = extract_entry(update_payload)

    after_update_payload = run_ok(
        run_cli,
        tmp_path,
        "search",
        "fresh-update-token",
        "--lexical-only",
    )
    hit = find_search_hit(extract_search_hits(after_update_payload), updated_entry["public_id"])
    assert hit is not None, after_update_payload

    explanation = hit.get("explanation")
    assert isinstance(explanation, dict), hit
    matched_fields = explanation.get("matched_fields")
    assert isinstance(matched_fields, list), explanation
    assert "body" in matched_fields


def test_build_recreates_missing_fts_tables_and_reindexes_content(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)

    add_payload = run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Rebuild baseline",
        "--type",
        "decision",
        "--author",
        "alice",
        "FTS rebuild baseline content for primary entry indexing.",
    )
    entry = extract_entry(add_payload)
    run_ok(
        run_cli,
        tmp_path,
        "event-add",
        "--event-type",
        "decision.recorded",
        "--summary",
        "Rebuild event baseline",
        "--body",
        "FTS rebuild baseline content for event indexing.",
        "--actor",
        "alice",
        "--resource",
        entry["public_id"],
    )

    first_build_payload = run_ok(run_cli, tmp_path, "build")
    assert first_build_payload["command"] == "system.build"
    assert table_exists(tmp_path, "entries_fts")
    assert table_exists(tmp_path, "events_fts")
    assert table_exists(tmp_path, "embeddings")
    assert select_count(tmp_path, "embeddings") == (
        select_count(tmp_path, "entries") + select_count(tmp_path, "events")
    )

    execute_sql(tmp_path, 'DROP TABLE "entries_fts"')
    execute_sql(tmp_path, 'DROP TABLE "events_fts"')
    assert not table_exists(tmp_path, "entries_fts")
    assert not table_exists(tmp_path, "events_fts")

    rebuilt_payload = run_ok(run_cli, tmp_path, "build")
    assert rebuilt_payload["command"] == "system.build"
    assert table_exists(tmp_path, "entries_fts")
    assert table_exists(tmp_path, "events_fts")
    assert select_count(tmp_path, "entries_fts") == select_count(tmp_path, "entries")
    assert select_count(tmp_path, "events_fts") == select_count(tmp_path, "events")
    assert select_count(tmp_path, "embeddings") == (
        select_count(tmp_path, "entries") + select_count(tmp_path, "events")
    )
