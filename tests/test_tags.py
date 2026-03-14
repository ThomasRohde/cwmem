from __future__ import annotations

from pathlib import Path

from tests.phase2_helpers import extract_entry, init_repo, run_ok


def test_tag_add_and_remove_round_trip_through_get(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    add_payload = run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Tag mutation target",
        "--type",
        "decision",
        "--author",
        "thomas",
        "Entry body for tag tests.",
    )
    entry = extract_entry(add_payload)

    # Assumption for Phase 2 integration: tag mutation commands take a resource ID
    # followed by repeated --tag flags.
    tag_add_payload = run_ok(
        run_cli,
        tmp_path,
        "tag-add",
        entry["public_id"],
        "--tag",
        "governance",
        "--tag",
        "review",
    )
    assert tag_add_payload["command"] == "memory.tag.add"

    after_add_payload = run_ok(run_cli, tmp_path, "get", entry["public_id"])
    tags_after_add = set(extract_entry(after_add_payload).get("tags", []))
    assert {"governance", "review"} <= tags_after_add

    tag_remove_payload = run_ok(
        run_cli,
        tmp_path,
        "tag-remove",
        entry["public_id"],
        "--tag",
        "governance",
    )
    assert tag_remove_payload["command"] == "memory.tag.remove"

    after_remove_payload = run_ok(run_cli, tmp_path, "get", entry["public_id"])
    tags_after_remove = set(extract_entry(after_remove_payload).get("tags", []))
    assert "governance" not in tags_after_remove
    assert "review" in tags_after_remove
