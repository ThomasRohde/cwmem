from __future__ import annotations

import json
from pathlib import Path

from tests.helpers import (
    assert_required_envelope_keys,
    flatten_strings,
    parse_envelope,
)


def test_guide_exposes_bootstrap_command_catalog(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "guide")
    payload = parse_envelope(completed.stdout, completed.stderr, completed.returncode)

    assert_required_envelope_keys(payload)
    assert payload["command"] == "system.guide"

    flattened = {item for item in flatten_strings(payload["result"])}
    serialized_result = json.dumps(payload["result"], sort_keys=True)

    assert "system.guide" in flattened or "system.guide" in serialized_result
    assert "system.init" in flattened or "system.init" in serialized_result
    assert "system.status" in flattened or "system.status" in serialized_result


def test_guide_mentions_bootstrap_aliases_or_catalog_entries(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "guide")
    payload = parse_envelope(completed.stdout, completed.stderr, completed.returncode)

    serialized_result = json.dumps(payload["result"], sort_keys=True).lower()
    for expected_fragment in ("guide", "init", "status"):
        assert expected_fragment in serialized_result, (
            f"`guide` result should mention `{expected_fragment}` in the command catalog.\n"
            f"Result payload: {payload['result']!r}"
        )


def test_guide_distinguishes_conceptual_and_plan_workflows(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "guide")
    payload = parse_envelope(completed.stdout, completed.stderr, completed.returncode)

    result = payload["result"]
    assert isinstance(result, dict), result
    workflows = result["workflows"]
    assert isinstance(workflows, list), workflows

    accepted_plan_values = {
        workflow.get("plan_value")
        for workflow in workflows
        if workflow.get("accepted_by_plan") is True
    }
    assert accepted_plan_values == {"sync-export", "sync-import"}

    bootstrap = next(workflow for workflow in workflows if workflow.get("name") == "bootstrap")
    assert bootstrap["kind"] == "sequence"
    assert bootstrap["accepted_by_plan"] is False


def test_guide_plan_command_lists_supported_workflow_values(run_cli, tmp_path: Path) -> None:
    completed = run_cli(tmp_path, "guide")
    payload = parse_envelope(completed.stdout, completed.stderr, completed.returncode)

    result = payload["result"]
    assert isinstance(result, dict), result
    command_catalog = result["command_catalog"]
    assert isinstance(command_catalog, list), command_catalog
    plan_entry = next(item for item in command_catalog if item.get("name") == "plan")

    serialized = json.dumps(plan_entry, sort_keys=True).lower()
    assert "sync-export" in serialized
    assert "sync-import" in serialized

