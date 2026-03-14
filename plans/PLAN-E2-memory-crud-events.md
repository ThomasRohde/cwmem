# Add memory CRUD and append-only event log

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, the CLI can create, read, list, and update memory entries, attach tags, append formal log events, and emit lifecycle events automatically when entries change. To see it working, run `uv run cwmem add`, `uv run cwmem get`, `uv run cwmem update`, and `uv run cwmem log`; the outputs should show deterministic public IDs, stable fingerprints, and follow-up events such as `memory.entry.created` and `memory.entry.updated`.

## Progress

- [ ] Verify that the Phase 1 package scaffold and command envelope already exist.
- [ ] Add the SQLite schema for entries, events, tags, and operational metadata.
- [ ] Implement deterministic IDs, fingerprinting, CRUD commands, and manual event creation.
- [ ] Emit lifecycle events automatically for entry mutations.
- [ ] Add export skeleton helpers for markdown and JSONL artifacts.
- [ ] Add tests for CRUD, tags, events, and fingerprint-protected updates.

## Surprises & Discoveries

No discoveries yet - this section will be populated during implementation.

## Decision Log

- Decision: Keep ULIDs as internal primary keys and expose sequential public IDs such as `mem-000001` and `evt-000001`.
  Rationale: Internal IDs remain globally unique while user-facing IDs stay stable and readable.
  Source: PRD Sections 14.1 and 14.2.

- Decision: Emit lifecycle events automatically by default when entries are created or updated.
  Rationale: The user explicitly chose automatic event emission, and the formal log is meant to capture memory lifecycle changes.
  Source: User clarification on 2026-03-14 and PRD Section 10.4.

- Decision: Export narrative entries as one markdown file per entry plus an aggregate JSONL file at `memory/entries/entries.jsonl`.
  Rationale: The user asked for both a human-review surface and a machine-efficient bulk format.
  Source: User clarification on 2026-03-14.

- Decision: Keep `sync export` explicit by default rather than running it after every write.
  Rationale: This keeps single-resource writes fast and predictable while the full sync workflow matures in a later phase.
  Source: User clarification on 2026-03-14.

## Outcomes & Retrospective

To be completed at major milestones and at plan completion.

## Context and Orientation

This phase assumes the repository already contains the scaffold from the bootstrap phase: `pyproject.toml`, `src/cwmem/__init__.py`, `src/cwmem/__main__.py`, the CLI module tree, and the shared envelope code. If `uv run cwmem guide` does not already work, stop and complete the bootstrap phase before continuing.

The main new runtime concepts are "entry", "event", and "fingerprint". An entry is a narrative memory record stored in SQLite and later exported to markdown and JSONL. An event is an append-only log record for audit and review. A fingerprint is a content hash used to detect stale updates. SQLite remains the operational store, and the checked-in `memory/` tree remains the collaboration surface, even though full import/export workflows arrive later.

The key files for this phase are `src/cwmem/core/store.py`, `src/cwmem/core/models.py`, `src/cwmem/core/ids.py`, `src/cwmem/core/fingerprints.py`, `src/cwmem/core/events.py`, `src/cwmem/core/export.py`, `src/cwmem/cli/write.py`, and `src/cwmem/cli/read.py`, plus tests in `tests/test_entry_crud.py`, `tests/test_events.py`, and `tests/test_tags.py`.

## Plan of Work

Expand `src/cwmem/core/store.py` so `cwmem init` creates the `entries`, `events`, `entry_tags`, `event_tags`, `event_resources`, and `metadata` tables. Store the next public-ID counters in `metadata` keys such as `next_mem_id` and `next_evt_id`, and initialize the schema version there too.

Implement `src/cwmem/core/ids.py` to generate ULIDs for internal identifiers and deterministic sequential public IDs for user-visible references. Implement `src/cwmem/core/fingerprints.py` so entry and event content hashes are stable across repeated serializations. Extend `src/cwmem/core/models.py` with typed request and response models for entry creation, entry updates, manual events, and log queries.

Implement `memory.add`, `memory.update`, `memory.get`, `memory.list`, `memory.log`, `memory.tag.add`, `memory.tag.remove`, and `memory.event.add`. `memory.add` should accept an inline body as the final positional argument, or JSON on stdin, and it should store title, type, status, author, tags, provenance, related IDs, entity refs, timestamps, and fingerprint. `memory.update` must support `--expected-fingerprint` and fail with a conflict-style error when the caller supplies a stale value.

Implement automatic lifecycle events in `src/cwmem/core/events.py` so entry creation and update commands append `memory.entry.created` and `memory.entry.updated` events unless the write was a dry run. Add export helpers in `src/cwmem/core/export.py` that can render a single entry to markdown front matter and to a JSONL row, plus an append-only event JSONL record. The full `sync export` command still arrives later; this phase only needs the core serialization functions and tests around them.

## Concrete Steps

1. Confirm the prerequisite scaffold is present.

   From the repository root, run:

    uv run cwmem guide

   Expected: `ok` is true and the `command` is `system.guide`.

2. Add the SQLite schema and ID/fingerprint helpers.

   Implement the core schema in `src/cwmem/core/store.py`. Add helper functions in `src/cwmem/core/ids.py` for ULIDs and public IDs. Add `src/cwmem/core/fingerprints.py` so the stored fingerprint changes only when the logical entry body or metadata changes.

3. Implement the write and read command handlers.

   In `src/cwmem/cli/write.py`, add `add`, `update`, `tag-add`, `tag-remove`, and `event-add`. In `src/cwmem/cli/read.py`, add `get`, `list`, and `log`. Each handler must return the standard envelope and canonical command IDs such as `memory.add` and `memory.log`.

4. Emit lifecycle events automatically.

   When `memory.add` succeeds, append a corresponding `memory.entry.created` event that links back to the new entry. When `memory.update` succeeds, append `memory.entry.updated`. The event log must stay append-only; updates create new events instead of rewriting old ones.

5. Add export skeleton helpers and tests.

   Write serialization helpers for `memory/entries/<public_id>.md`, `memory/entries/entries.jsonl`, and `memory/events/events.jsonl`. Add tests for entry creation, update with matching fingerprint, update rejection with stale fingerprint, tag mutation, manual event creation, and auto-emitted lifecycle events.

6. Validate from the repository root.

    uv run cwmem add --title "Capability model alignment" --type decision --author thomas --tags capability-model --tags governance "We aligned the EA capability model with the BCM baseline."
    uv run cwmem get mem-000001
    uv run cwmem update mem-000001 --expected-fingerprint <fingerprint-from-get> --title "Capability model alignment v2"
    uv run cwmem log --resource mem-000001
    uv run pytest --tb=short

   Expected: the first add returns `public_id: mem-000001`, the update returns a new fingerprint, and the log contains both the create and update events for the same resource.

## Validation and Acceptance

Run `uv run cwmem add`, `uv run cwmem get`, `uv run cwmem list`, `uv run cwmem update`, and `uv run cwmem log` from the repository root.

Expected behavior: entries persist to SQLite, list results are deterministic, updates require the correct fingerprint when the flag is supplied, and the event log is append-only. A successful `memory.add` response should include the stored fingerprint, tags, timestamps, and canonical command ID. A successful `memory.log --resource mem-000001` response should include at least one `memory.entry.created` event and one `memory.entry.updated` event after the update command has run.

Then run:

    uv run pytest --tb=short
    uv run ruff check src/ tests/
    uv run pyright src/

Expected behavior: the new CRUD and event tests pass, lint stays clean, and type checking succeeds.

## Idempotence and Recovery

Do not make `memory.add` silently retry without an idempotency key; that safety feature belongs to a later hardening phase. For now, retries without a key create new resources by design. `memory.update` must be safe to retry when the same mutation is reapplied with the current fingerprint.

If a schema change is interrupted during development, delete the temporary test database and rerun `cwmem init`; do not delete a real user's `.cwmem/memory.sqlite` once the repository contains meaningful data. Export helpers must be pure functions so they can be rerun without side effects.

## Artifacts and Notes

A successful `memory.get` result should resemble:

    {
      "command": "memory.get",
      "result": {
        "entry": {
          "public_id": "mem-000001",
          "title": "Capability model alignment v2",
          "type": "decision",
          "tags": ["capability-model", "governance"],
          "fingerprint": "sha256:..."
        }
      }
    }

A successful `memory.log` result for that resource should contain event types such as `memory.entry.created` and `memory.entry.updated`, with monotonically increasing timestamps and stable public IDs.

## Interfaces and Dependencies

The primary modules are `cwmem.core.store`, `cwmem.core.ids`, `cwmem.core.fingerprints`, `cwmem.core.events`, and `cwmem.core.export`. The key functions that must exist are `ensure_schema(...)`, `next_public_id(kind: str) -> str`, `compute_entry_fingerprint(entry: EntryRecord) -> str`, `append_event(...) -> EventRecord`, `render_entry_markdown(entry: EntryRecord) -> str`, and `render_entry_jsonl(entry: EntryRecord) -> str`.

Extend the typed models with `EntryRecord`, `EventRecord`, `CreateEntryInput`, `UpdateEntryInput`, `TagMutationInput`, and `LogQuery`. The command handlers in `cwmem.cli.write` and `cwmem.cli.read` should depend on those models instead of passing raw dictionaries around, because later search, graph, and sync phases will reuse the same records.
