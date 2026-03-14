# Add deterministic sync export and import workflows

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, the runtime SQLite database and the checked-in `memory/` tree can round-trip without logical drift. To see it working, run `uv run cwmem sync export`, inspect the rendered markdown and JSONL artifacts, then run `uv run cwmem sync import --dry-run` and `uv run cwmem sync export --check`; the commands should prove the database and artifacts agree.

## Progress

- [ ] Verify that entries, events, embeddings, and graph data already exist and can be queried.
- [ ] Implement deterministic export for entries, events, graph files, taxonomy files, and the export manifest.
- [ ] Implement import planning and application from checked-in artifacts back into SQLite.
- [ ] Add `sync export --check` and round-trip tests.
- [ ] Validate determinism across repeated export/import cycles.

## Surprises & Discoveries

No discoveries yet - this section will be populated during implementation.

## Decision Log

- Decision: `sync export` remains explicit by default rather than running after every write.
  Rationale: The user chose explicit sync so normal writes stay fast and predictable.
  Source: User clarification on 2026-03-14.

- Decision: Export entries as per-entry markdown plus `memory/entries/entries.jsonl`, and export the graph as `memory/graph/nodes.jsonl` and `memory/graph/edges.jsonl`.
  Rationale: The collaboration surface must serve both human review and machine-efficient bulk processing.
  Source: User clarification on 2026-03-14 and PRD Sections 7.2 and 16.

- Decision: The manifest field named `generated_at` is derived deterministically from the exported snapshot instead of the wall-clock time of the export command.
  Rationale: The PRD requires both a timestamp field and byte-stable exports, so the timestamp must be stable when the logical snapshot is unchanged.
  Source: PRD Sections 16.4 and 24.3.

## Outcomes & Retrospective

To be completed at major milestones and at plan completion.

## Context and Orientation

This phase assumes the repository already contains working entry, event, search, embedding, and graph features. If `uv run cwmem graph show` or `uv run cwmem search --expand-graph` does not already work, finish the earlier phases first.

The phrase "sync export" means rendering checked-in artifacts from SQLite into `memory/`. The phrase "sync import" means rebuilding or updating SQLite from those artifacts. The key implementation files are `src/cwmem/core/export.py`, `src/cwmem/core/importer.py`, `src/cwmem/core/validator.py`, `src/cwmem/cli/sync.py`, and tests in `tests/test_sync_export.py`, `tests/test_sync_import.py`, and `tests/test_round_trip.py`.

The exported artifacts must include per-entry markdown, aggregate entry JSONL, append-only event JSONL, graph node and edge JSONL, taxonomy JSON, and `memory/manifests/export-manifest.json`. All file order, JSON serialization, and timestamp handling must be deterministic.

## Plan of Work

Implement `src/cwmem/core/export.py` so it reads canonical SQLite records, sorts them deterministically, renders markdown and JSONL artifacts, computes file fingerprints, and writes a manifest that captures counts, source DB fingerprint, file fingerprints, embedding-model metadata, and a deterministic snapshot timestamp.

Implement `src/cwmem/core/importer.py` so it reads the manifest and exported artifacts, validates required files, computes an import plan, applies inserts and updates to SQLite inside a transaction, rebuilds FTS and embeddings as needed, and returns counts for created, updated, skipped, and removed resources. Support `--dry-run` and `--fail-on-drift` for sync commands in this phase, because the PRD already requires them on `sync import` and `sync export`.

Wire `memory.sync.export` and `memory.sync.import` in `src/cwmem/cli/sync.py`. `sync export --check` should compare the live database snapshot against the existing on-disk manifest and fail with a conflict-style envelope when files are stale. `sync import --dry-run` should return the proposed changes without mutating SQLite.

Add round-trip tests that export a populated database, delete or recreate the database in a temporary directory, import from the artifacts, rebuild indexes, and confirm that a second export produces the same manifest fingerprint and byte-identical files.

## Concrete Steps

1. Confirm the prerequisite domain behavior.

   From the repository root, run:

    uv run cwmem list --limit 5
    uv run cwmem graph show mem-000001 --depth 1

   Expected: the repository already contains data and graph behavior worth exporting.

2. Implement deterministic export.

   In `src/cwmem/core/export.py`, add file renderers for entries, events, graph nodes, graph edges, and the export manifest. Use canonical sorting and `orjson` options that preserve stable key ordering and whitespace.

3. Implement import planning and application.

   In `src/cwmem/core/importer.py`, parse the manifest and artifacts, validate schema and counts, compute an import plan, and apply it transactionally. Rebuild FTS, embeddings, and inferred edges after the import so the operational cache matches the imported state.

4. Wire the sync CLI.

   Add `sync export` and `sync import` handlers in `src/cwmem/cli/sync.py`. `sync export` should default `--output-dir` to `memory/`. `sync export --check` should return `ok: false` when the live DB fingerprint differs from the manifest fingerprint on disk.

5. Add round-trip tests.

   Write tests that export twice without logical changes and confirm byte-identical results, import an exported snapshot into a fresh database, and verify that `sync export --check` fails when a checked-in artifact is manually modified in a temporary test repo.

6. Validate from the repository root.

    uv run cwmem sync export
    uv run cwmem sync export --check
    uv run cwmem sync import --dry-run
    uv run pytest --tb=short

   Expected: export writes deterministic files under `memory/`, `--check` succeeds immediately after a clean export, dry-run import reports zero or more proposed changes without mutating SQLite, and the round-trip tests pass.

## Validation and Acceptance

Run:

    uv run cwmem sync export
    uv run cwmem sync export --check

Expected behavior: the export command writes `memory/entries/*.md`, `memory/entries/entries.jsonl`, `memory/events/events.jsonl`, `memory/graph/nodes.jsonl`, `memory/graph/edges.jsonl`, and `memory/manifests/export-manifest.json`. Immediately re-running `sync export --check` should return `ok: true`.

Then run:

    uv run cwmem sync import --dry-run

Expected behavior: the result includes a concrete change summary and impacted resources, but the command does not mutate SQLite while `dry_run` is true.

Finally run:

    uv run pytest --tb=short
    uv run ruff check src/ tests/
    uv run pyright src/

Expected behavior: round-trip tests pass and export determinism is preserved.

## Idempotence and Recovery

Repeated `sync export` runs with no logical data changes must produce byte-identical files. Repeated `sync import` runs against identical artifacts must either report no changes or only harmless cache rebuilds. Keep import application inside a single SQLite transaction so a failure rolls back cleanly.

If a manual edit makes checked-in artifacts stale, the recovery path is to inspect the diff, rerun `sync export`, and then rerun `sync export --check`. If import validation fails, stop before mutating the database and return the specific schema or drift errors to the caller.

## Artifacts and Notes

A manifest excerpt should resemble:

    {
      "export_version": "1.0",
      "source_db_fingerprint": "sha256:...",
      "counts": {"entries": 12, "events": 31, "entities": 5, "edges": 9},
      "files": {
        "entries/entries.jsonl": "sha256:...",
        "graph/edges.jsonl": "sha256:..."
      },
      "model": {"name": "...", "version": "..."},
      "generated_at": "2026-03-14T10:10:00Z"
    }

## Interfaces and Dependencies

The critical interfaces are `export_snapshot(...) -> ExportResult`, `compute_manifest(...) -> ExportManifest`, `import_snapshot(...) -> ImportResult`, and `check_export_freshness(...) -> ValidationIssue | None`. Extend the typed models with `ExportManifest`, `ExportFileRecord`, `ImportPlan`, and `ImportResult`.

This phase depends on `orjson`, stdlib `sqlite3`, the existing search and embedding rebuild paths, and the graph export helpers introduced earlier. Keep export and import code file-scoped and deterministic so the later safety phase can wrap them in richer workflow plans.
