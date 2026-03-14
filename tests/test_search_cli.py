from __future__ import annotations

from pathlib import Path

from tests.phase2_helpers import (
    extract_entry,
    extract_event,
    init_repo,
    run_ok,
)
from tests.phase3_helpers import extract_search_hits, find_search_hit, search_hit_resource_id


def test_search_filters_and_limit_are_deterministic(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    alpha = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Governance radar alpha",
            "--type",
            "decision",
            "--author",
            "alice",
            "--tag",
            "strategy",
            "Lexical filter matrix candidate alpha.",
        )
    )
    beta = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Governance radar beta",
            "--type",
            "decision",
            "--author",
            "alice",
            "--tag",
            "strategy",
            "Lexical filter matrix candidate beta.",
        )
    )
    run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Governance radar wrong-author",
        "--type",
        "decision",
        "--author",
        "bob",
        "--tag",
        "strategy",
        "Lexical filter matrix candidate wrong-author.",
    )
    run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Governance radar wrong-type",
        "--type",
        "finding",
        "--author",
        "alice",
        "--tag",
        "strategy",
        "Lexical filter matrix candidate wrong-type.",
    )
    run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Governance radar wrong-tag",
        "--type",
        "decision",
        "--author",
        "alice",
        "--tag",
        "review",
        "Lexical filter matrix candidate wrong-tag.",
    )

    full_payload = run_ok(
        run_cli,
        tmp_path,
        "search",
        "lexical filter matrix",
        "--lexical-only",
        "--tag",
        "strategy",
        "--type",
        "decision",
        "--author",
        "alice",
        "--limit",
        "10",
    )
    full_ids = [search_hit_resource_id(hit) for hit in extract_search_hits(full_payload)]
    assert set(full_ids) == {alpha["public_id"], beta["public_id"]}

    limited_once = run_ok(
        run_cli,
        tmp_path,
        "search",
        "lexical filter matrix",
        "--lexical-only",
        "--tag",
        "strategy",
        "--type",
        "decision",
        "--author",
        "alice",
        "--limit",
        "1",
    )
    limited_twice = run_ok(
        run_cli,
        tmp_path,
        "search",
        "lexical filter matrix",
        "--lexical-only",
        "--tag",
        "strategy",
        "--type",
        "decision",
        "--author",
        "alice",
        "--limit",
        "1",
    )
    limited_once_ids = [search_hit_resource_id(hit) for hit in extract_search_hits(limited_once)]
    limited_twice_ids = [search_hit_resource_id(hit) for hit in extract_search_hits(limited_twice)]
    assert limited_once_ids == full_ids[:1]
    assert limited_twice_ids == full_ids[:1]


def test_search_from_and_to_filters_event_hits_by_occurred_at(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    entry = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Date filter anchor",
            "--type",
            "note",
            "--author",
            "alice",
            "Anchor entry for event date filter tests.",
        )
    )
    older_event = extract_event(
        run_ok(
            run_cli,
            tmp_path,
            "event-add",
            "--event-type",
            "timeline.snapshot",
            "--summary",
            "Older timeline event",
            "--body",
            "Event window token for the older snapshot.",
            "--actor",
            "alice",
            "--resource",
            entry["public_id"],
            "--occurred-at",
            "2024-01-15T00:00:00Z",
        )
    )
    newer_event = extract_event(
        run_ok(
            run_cli,
            tmp_path,
            "event-add",
            "--event-type",
            "timeline.snapshot",
            "--summary",
            "Newer timeline event",
            "--body",
            "Event window token for the newer snapshot.",
            "--actor",
            "alice",
            "--resource",
            entry["public_id"],
            "--occurred-at",
            "2025-01-15T00:00:00Z",
        )
    )

    search_payload = run_ok(
        run_cli,
        tmp_path,
        "search",
        "event window token",
        "--lexical-only",
        "--from",
        "2024-06-01T00:00:00Z",
        "--to",
        "2025-12-31T23:59:59Z",
    )
    hit_ids = {search_hit_resource_id(hit) for hit in extract_search_hits(search_payload)}
    assert newer_event["public_id"] in hit_ids
    assert older_event["public_id"] not in hit_ids


def test_search_semantic_only_returns_hits_after_build(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    entry = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Business capability baseline",
            "--type",
            "decision",
            "--author",
            "alice",
            "Business capability baseline alignment for semantic retrieval verification.",
        )
    )
    run_ok(run_cli, tmp_path, "build")

    payload = run_ok(
        run_cli,
        tmp_path,
        "search",
        "business capability baseline alignment",
        "--semantic-only",
        "--limit",
        "5",
    )
    assert payload["command"] == "memory.search"
    hits = extract_search_hits(payload)
    hit = find_search_hit(hits, entry["public_id"])
    assert hit is not None, hits
    assert "semantic" in hit["match_modes"]
    explanation = hit["explanation"]
    assert isinstance(explanation, dict), hit
    assert isinstance(explanation.get("semantic_rank"), int), explanation
