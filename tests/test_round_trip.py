from __future__ import annotations

from pathlib import Path

from tests.phase2_helpers import init_repo
from tests.phase6_helpers import (
    copy_memory_tree,
    count_records,
    export_memory_snapshot,
    run_sync_ok,
    seed_sync_repo,
)


def test_sync_round_trip_reimports_exported_artifacts_into_fresh_sqlite(
    run_cli, tmp_path: Path
) -> None:
    source_repo = tmp_path / "source"
    destination_repo = tmp_path / "destination"
    source_repo.mkdir()
    destination_repo.mkdir()

    seed_sync_repo(run_cli, source_repo)
    run_sync_ok(run_cli, source_repo, "sync", "export")
    expected_snapshot = export_memory_snapshot(source_repo)
    expected_counts = count_records(source_repo)

    init_repo(run_cli, destination_repo)
    copy_memory_tree(source_repo, destination_repo)

    import_payload = run_sync_ok(run_cli, destination_repo, "sync", "import")
    assert import_payload["command"] == "memory.sync.import"
    assert count_records(destination_repo) == expected_counts

    rerender_payload = run_sync_ok(run_cli, destination_repo, "sync", "export")
    assert rerender_payload["command"] == "memory.sync.export"
    assert export_memory_snapshot(destination_repo) == expected_snapshot
