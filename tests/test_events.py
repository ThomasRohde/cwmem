from __future__ import annotations

import json
from pathlib import Path

from tests.phase2_helpers import (
    extract_entry,
    extract_event,
    extract_events,
    init_repo,
    run_ok,
)


def test_log_contains_automatic_lifecycle_events_for_add_and_update(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)

    add_payload = run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Lifecycle audit target",
        "--type",
        "decision",
        "--author",
        "thomas",
        "Created for lifecycle verification.",
    )
    entry = extract_entry(add_payload)

    initial_log_payload = run_ok(run_cli, tmp_path, "log", "--resource", entry["public_id"])
    initial_events = extract_events(initial_log_payload)
    initial_event_types = {event["event_type"] for event in initial_events}
    assert "memory.entry.created" in initial_event_types

    run_ok(
        run_cli,
        tmp_path,
        "update",
        entry["public_id"],
        "--expected-fingerprint",
        entry["fingerprint"],
        "--title",
        "Lifecycle audit target v2",
    )

    updated_log_payload = run_ok(run_cli, tmp_path, "log", "--resource", entry["public_id"])
    updated_events = extract_events(updated_log_payload)
    updated_event_types = {event["event_type"] for event in updated_events}
    assert {"memory.entry.created", "memory.entry.updated"} <= updated_event_types
    assert all(event["public_id"].startswith("evt-") for event in updated_events)


def test_event_add_appends_manual_event_visible_in_resource_log(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)

    add_payload = run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Manual event target",
        "--type",
        "finding",
        "--author",
        "thomas",
        "Entry body for manual event attachment.",
    )
    entry = extract_entry(add_payload)

    # Assumption for Phase 2 integration: event-add accepts explicit event metadata
    # via --event-type/--summary/--body/--actor/--resource and repeated --tag flags.
    event_payload = run_ok(
        run_cli,
        tmp_path,
        "event-add",
        "--event-type",
        "decision.recorded",
        "--summary",
        "Recorded the governance decision",
        "--body",
        "This event confirms the manual governance note.",
        "--actor",
        "thomas",
        "--resource",
        entry["public_id"],
        "--tag",
        "governance",
    )
    assert event_payload["command"] == "memory.event.add"

    created_event = extract_event(event_payload)
    assert created_event["public_id"].startswith("evt-")
    assert created_event["event_type"] == "decision.recorded"

    serialized_event = json.dumps(created_event, sort_keys=True)
    assert "Recorded the governance decision" in serialized_event

    log_payload = run_ok(run_cli, tmp_path, "log", "--resource", entry["public_id"])
    events = extract_events(log_payload)
    event_types = {event["event_type"] for event in events}
    assert "decision.recorded" in event_types
    assert "memory.entry.created" in event_types

