from __future__ import annotations

import json
from pathlib import Path

from tests.phase2_helpers import init_repo
from tests.phase6_helpers import (
    copy_memory_tree,
    count_records,
    extract_sync_result,
    run_sync_any,
    run_sync_ok,
    seed_sync_repo,
)


def test_sync_import_dry_run_reports_plan_without_mutating_sqlite(
    run_cli, tmp_path: Path
) -> None:
    source_repo = tmp_path / "source"
    destination_repo = tmp_path / "destination"
    source_repo.mkdir()
    destination_repo.mkdir()

    seed_sync_repo(run_cli, source_repo)
    run_sync_ok(run_cli, source_repo, "sync", "export")

    init_repo(run_cli, destination_repo)
    copy_memory_tree(source_repo, destination_repo)
    before_counts = count_records(destination_repo)

    completed, payload = run_sync_any(run_cli, destination_repo, "sync", "import", "--dry-run")
    assert completed.returncode == 0, completed
    assert payload["command"] == "memory.sync.import"

    result = extract_sync_result(payload)
    dry_run = result.get("dry_run", payload.get("dry_run"))
    assert dry_run is True, payload
    assert count_records(destination_repo) == before_counts

    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "dry_run" in serialized
    assert any(
        token in serialized for token in ("changes", "proposed", "plan", "impacted")
    ), payload
