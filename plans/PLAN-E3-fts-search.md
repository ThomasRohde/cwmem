# Add SQLite FTS5 search and basic validation

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, `cwmem search` can find entries through SQLite FTS5 lexical matching, and `cwmem stats` plus `cwmem validate` can prove that the search index is aligned with the primary tables. To see it working, add a few entries and run `uv run cwmem search "capability model" --lexical-only`; the result should show ordered lexical hits with explanation fields and deterministic filtering.

## Progress

- [ ] Verify that the CRUD and event-log phase is already working.
- [ ] Add FTS5 tables and rebuild helpers for lexical indexing.
- [ ] Implement `memory.search`, `memory.stats`, and a basic `memory.validate` command.
- [ ] Add deterministic lexical filters and ranking output.
- [ ] Add unit and integration tests for FTS indexing and query behavior.

## Surprises & Discoveries

No discoveries yet - this section will be populated during implementation.

## Decision Log

- Decision: Keep lexical search entirely inside SQLite using FTS5 virtual tables.
  Rationale: The PRD calls for SQLite FTS5 BM25 and does not require any external indexing service.
  Source: PRD Sections 8.2 and 15.3.

- Decision: Rebuild FTS indexes on `cwmem build`, but also update the affected rows transactionally during normal entry and event writes.
  Rationale: This keeps search fresh for normal use while preserving a full rebuild path for repair.
  Source: PRD Sections 12.9 and 15.3.

- Decision: Support lexical explanations now and reject `--semantic-only` with a stable validation error until the semantic phase lands.
  Rationale: The command surface must be stable early, but the implementation should not pretend semantic search exists before embeddings are available.
  Source: PRD Sections 11, 12.4, and 25 Phase 4.

## Outcomes & Retrospective

To be completed at major milestones and at plan completion.

## Context and Orientation

This phase assumes entries, events, tags, and lifecycle events are already stored in SQLite and accessible through working CLI commands. If `uv run cwmem add` and `uv run cwmem log` do not already work, complete the previous phase before continuing.

The phrase "FTS5" refers to SQLite's full-text-search virtual table feature. It stores a tokenized search view over selected text columns and returns ranked lexical matches. In this project, the lexical index should cover entry titles, entry bodies, entry tags, event summaries, event bodies, and later entity names and aliases. The key implementation files are `src/cwmem/core/fts.py`, `src/cwmem/core/store.py`, `src/cwmem/core/validator.py`, `src/cwmem/cli/read.py`, and `src/cwmem/cli/maintenance.py`.

## Plan of Work

Extend the SQLite schema to include `entries_fts` and `events_fts` immediately, plus an empty `entities` table and `entities_fts` virtual table so the schema shape matches the long-term data model before the graph phase arrives. Implement `src/cwmem/core/fts.py` with helpers to rebuild indexes from the canonical tables, upsert changed rows after writes, and query FTS with filters for tag, type, author, and date range.

Implement `memory.search` in `src/cwmem/cli/read.py`. The result payload should include hit IDs, resource type, score, matched fields, and a small explanation object that says the hit came from lexical search. Implement `memory.stats` in `src/cwmem/cli/maintenance.py` so it reports row counts for tables and FTS indexes, plus whether the latest build has been run. Implement a basic `memory.validate` that checks schema presence, primary-table row counts, and FTS consistency.

Add tests in `tests/test_fts.py`, `tests/test_search_cli.py`, and `tests/test_validate_basic.py` to cover indexing, updates, filters, and validation failures.

## Concrete Steps

1. Verify the CRUD baseline.

   From the repository root, run:

    uv run cwmem add --title "Search baseline" --type note "Lexical search should find this sentence."
    uv run cwmem log --limit 5

   Expected: both commands return `ok: true` and the created entry is visible to later search tests.

2. Add the FTS schema and rebuild helpers.

   In `src/cwmem/core/store.py`, add the FTS virtual tables and any supporting SQL needed for rebuilds. In `src/cwmem/core/fts.py`, add functions to rebuild all indexed resources and to update a single resource after create or update commands.

3. Implement `memory.search`.

   Wire `cwmem search <query>` in `src/cwmem/cli/read.py`. Support `--tag`, `--type`, `--author`, `--from`, `--to`, `--lexical-only`, and `--limit`. If `--semantic-only` is supplied before the semantic phase exists, return a validation error envelope rather than silently falling back.

4. Implement `memory.stats` and the first version of `memory.validate`.

   `stats` should report table counts, FTS counts, and the last build timestamp if present. `validate` should verify that required tables exist and that the number of indexed FTS rows matches the number of source rows.

5. Add tests.

   Write tests that prove new entries are searchable immediately, updated entries refresh their indexed text, filters narrow the result set deterministically, and validation reports mismatches when the FTS tables are intentionally desynchronized in a temporary test database.

6. Run the repository commands from the root.

    uv run cwmem build
    uv run cwmem search "capability model" --lexical-only --limit 5
    uv run cwmem stats
    uv run cwmem validate
    uv run pytest --tb=short

   Expected: `build` refreshes indexes, `search` returns lexical hits with explanations, `stats` shows matching table and FTS counts, and `validate` returns `ok: true` when the index is healthy.

## Validation and Acceptance

Run:

    uv run cwmem search "capability model" --lexical-only

Expected behavior: the result set is sorted deterministically, every hit includes a lexical explanation, and filters only remove results that do not match the requested tag, type, author, or date range.

Run:

    uv run cwmem stats
    uv run cwmem validate

Expected behavior: `stats` reports counts for `entries`, `events`, `entries_fts`, and `events_fts`; `validate` confirms those counts align and returns a clear error when they do not.

Then run the standard checks:

    uv run pytest --tb=short
    uv run ruff check src/ tests/
    uv run pyright src/

Expected behavior: search tests pass and the repository stays clean under linting and type checking.

## Idempotence and Recovery

`cwmem build` must be safe to run repeatedly; it should truncate and rebuild FTS tables from the canonical records without changing logical data. Search reads are naturally idempotent. If the FTS schema changes during development, rerun `cwmem build` instead of hand-editing virtual tables.

If validation reports index drift, the recovery path is `cwmem build` followed by `cwmem validate`. Do not repair FTS rows manually in production code; keep the rebuild path authoritative.

## Artifacts and Notes

A lexical search result should include an explanation object similar to:

    {
      "resource_id": "mem-000001",
      "resource_type": "entry",
      "match_modes": ["lexical"],
      "explanation": {
        "lexical_rank": 1,
        "matched_fields": ["title", "body", "tags"]
      }
    }

## Interfaces and Dependencies

The main interfaces are `rebuild_fts(...)`, `upsert_entry_fts(...)`, `search_lexical(query: SearchQuery) -> list[SearchHit]`, and `validate_fts_consistency(...)`. Extend `cwmem.core.models` with `SearchQuery`, `SearchHit`, `StatsResult`, and `ValidationIssue`.

The implementation relies only on stdlib `sqlite3` plus SQLite FTS5. Keep the scoring logic small and explicit so later hybrid reranking can merge lexical and semantic candidates without rewriting the lexical path.
