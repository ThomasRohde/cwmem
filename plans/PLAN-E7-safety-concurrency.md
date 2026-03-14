# Add dry-run, locking, idempotency, and verify workflows

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, mutating commands become safe for repeated agent execution: they can preview changes with `--dry-run`, serialize writes with an exclusive lock, deduplicate retried requests with `--idempotency-key`, and prove postconditions with `validate` and `verify`. To see it working, run `uv run cwmem add ... --dry-run`, repeat a write with the same idempotency key, and run `uv run cwmem verify`; the CLI should explain what would change, prevent conflicting writes, and confirm the repository is internally consistent.

## Progress

- [ ] Verify that sync export/import already work on a non-trivial dataset.
- [ ] Add sidecar locking and lock-owner reporting.
- [ ] Add idempotency-key storage and replay behavior for retried writes.
- [ ] Extend mutating commands with `--dry-run` and concrete change summaries.
- [ ] Implement `plan`, `validate`, `apply`, and `verify` workflow support for sync and batch operations.
- [ ] Add tests for lock contention, dry-run behavior, idempotent retries, and verification failures.

## Surprises & Discoveries

No discoveries yet - this section will be populated during implementation.

## Decision Log

- Decision: Use `portalocker` for the v1 locking implementation even though the PRD lists it as optional.
  Rationale: Cross-platform exclusive locking is a core safety requirement, and a proven library is safer than hand-rolled file locking.
  Source: PRD Section 22.1 plus implementation decision for this plan.

- Decision: Store idempotency keys in a dedicated SQLite table rather than overloading generic metadata rows.
  Rationale: Replays need request hashing, timestamps, and result references, which fit naturally in a relational table.
  Source: PRD Section 18.5.

- Decision: Default workflow plan artifacts live under `.cwmem/plans/` unless the caller passes `--plan-out`.
  Rationale: The artifacts need a predictable local home, but callers still need explicit control when they want to review or commit them elsewhere.
  Source: PRD Sections 12.7, 12.8, and 18.4.

## Outcomes & Retrospective

To be completed at major milestones and at plan completion.

## Context and Orientation

This phase assumes sync export/import and graph/search behavior already exist. If `uv run cwmem sync export --check` does not already succeed on a populated dataset, stop and complete the sync phase first.

The new concepts are "exclusive sidecar lock", "idempotency record", and "verify". The sidecar lock is a file at `.cwmem/memory.sqlite.lock` that describes the active writer. An idempotency record remembers that a prior write with the same key and request hash already succeeded. `verify` is the postcondition command that proves tables, indexes, graph projections, and exported artifacts agree. The key files are `src/cwmem/core/locking.py`, `src/cwmem/core/planner.py`, `src/cwmem/core/validator.py`, `src/cwmem/cli/write.py`, `src/cwmem/cli/sync.py`, and `src/cwmem/cli/maintenance.py`.

## Plan of Work

Add `portalocker` to `pyproject.toml` and implement `src/cwmem/core/locking.py` so mutating commands acquire `.cwmem/memory.sqlite.lock`, record PID, hostname, timestamp, command, and request ID, and either wait or fail with `ERR_LOCK_HELD` depending on `--wait-lock`. Keep reads lock-free.

Add an `idempotency_keys` table in `src/cwmem/core/store.py` with columns for key, command ID, request hash, result resource ID, created timestamp, and last response payload. Extend all write handlers in `src/cwmem/cli/write.py` and `src/cwmem/cli/sync.py` so they accept `--idempotency-key`, check for an existing matching request, and replay the stored result when the key and request hash match.

Implement `--dry-run` for all mutating commands. The result payload must include `dry_run: true`, proposed changes, summary counts, and impacted resources, but it must not change SQLite, exports, or lock metadata beyond the transient lock needed for evaluation. Add `src/cwmem/core/planner.py` to render plan artifacts for risky sync and batch operations, and extend the CLI with `plan`, `validate`, `apply`, and `verify` behavior where the PRD requires it.

Expand `src/cwmem/core/validator.py` and `src/cwmem/cli/maintenance.py` so `validate` covers schema correctness, referential integrity, taxonomy compliance, duplicate/public-ID invariants, graph edge validity, and export determinism, while `verify` asserts postconditions such as manifest fingerprint matches, FTS row counts, graph edge counts, and embedding-model metadata.

## Concrete Steps

1. Confirm the sync baseline.

   From the repository root, run:

    uv run cwmem sync export
    uv run cwmem sync export --check

   Expected: both commands succeed before safety hardening starts.

2. Implement the lock layer.

   Add `portalocker` to the project dependencies. Create `src/cwmem/core/locking.py` and ensure every mutating command acquires the sidecar lock before it reads or writes SQLite. Return `ERR_LOCK_HELD` with lock-owner details when a conflicting writer exists.

3. Implement idempotency storage and replay.

   Add the `idempotency_keys` table and shared helpers that hash the normalized request payload. Replay prior success envelopes only when the command ID, key, and request hash all match.

4. Add `--dry-run` and workflow plan artifacts.

   Extend `add`, `update`, `tag-add`, `tag-remove`, `event-add`, `entity-add`, `link`, `sync export`, and `sync import` so each can return a concrete dry-run change summary. For sync and batch operations, write a plan artifact under `.cwmem/plans/` by default, or to the path supplied through `--plan-out`.

5. Implement `validate` and `verify` to the full v1 contract.

   `validate` should detect broken references, duplicate public IDs, invalid taxonomy values, graph inconsistencies, and stale exports. `verify` should assert postconditions after export/import workflows, including manifest fingerprint matches, table/FTS parity, and model metadata correctness.

6. Add tests and validate from the repository root.

    uv run cwmem add --title "Safety test" --type note --dry-run "This should not persist."
    uv run cwmem add --title "Idempotent write" --type note --idempotency-key demo-1 "This should persist once."
    uv run cwmem add --title "Idempotent write" --type note --idempotency-key demo-1 "This should persist once."
    uv run cwmem sync export --dry-run --plan-out .cwmem/plans/export-plan.json
    uv run cwmem verify
    uv run pytest --tb=short

   Expected: the dry run reports proposed changes without persisting them, the repeated idempotent write returns the original resource ID, the sync plan artifact is created, and `verify` returns `ok: true` when the repository is consistent.

## Validation and Acceptance

Run a mutating command with `--dry-run`.

Expected behavior: the result contains `dry_run: true`, change counts, and impacted resources, but a follow-up `get` or `list` proves no mutation occurred.

Run the same mutating command twice with the same `--idempotency-key` and equivalent payload.

Expected behavior: the second response replays the first result rather than creating a duplicate resource. The stored idempotency record references the original resource ID and command.

Use the locking tests and `verify` command to prove safety behavior:

    uv run pytest tests/test_locking.py -q
    uv run cwmem verify

Expected behavior: concurrent writes produce `ERR_LOCK_HELD`, reads remain parallel-safe, and `verify` confirms export, search, graph, and embedding invariants.

## Idempotence and Recovery

Idempotency keys are the safe retry path for agents. If a write fails before commit, the key should not be recorded as successful. If a write succeeds and the client retries, replay the stored success envelope rather than applying the mutation again.

If a lock file remains after a crash, the recovery path is to read its metadata, confirm the recorded PID is no longer alive, and then remove or replace the stale lock in the next writer. Do not tell users to delete the lock blindly; always surface the owner details first.

## Artifacts and Notes

A dry-run result should resemble:

    {
      "command": "memory.add",
      "result": {
        "dry_run": true,
        "summary": {"entries_to_create": 1, "events_to_create": 1},
        "impacted_resources": ["mem-000021", "evt-000044"]
      }
    }

A lock error should resemble:

    {
      "ok": false,
      "errors": [
        {
          "code": "ERR_LOCK_HELD",
          "retryable": true,
          "details": {"pid": 1234, "command": "memory.sync.export"}
        }
      ]
    }

## Interfaces and Dependencies

The key interfaces are `acquire_lock(...)`, `release_lock(...)`, `record_idempotent_success(...)`, `replay_idempotent_success(...)`, `plan_changes(...)`, `validate_repository(...)`, and `verify_repository(...)`. Add typed models for `LockInfo`, `IdempotencyRecord`, `DryRunSummary`, `PlanArtifact`, and `VerificationResult`.

This phase depends on `portalocker`, stdlib `sqlite3`, and the existing export/import/search/graph modules. Keep lock ownership, idempotency hashing, and verification logic centralized so every mutating command uses the same safety rules.
