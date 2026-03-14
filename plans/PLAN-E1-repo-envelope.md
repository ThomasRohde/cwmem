# Add repository scaffold and CLI envelope

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, a brand-new checkout can be bootstrapped with `uv sync`, and the local CLI can answer `guide`, `init`, and `status` through one stable JSON envelope on stdout. To see it working, run `uv run cwmem guide`, `uv run cwmem init`, and `uv run cwmem status`; each command should return `ok: true`, a canonical dotted `command`, and a non-null `result` payload.

## Progress

- [ ] Create the package scaffold, build metadata, and repository housekeeping files.
- [ ] Implement the shared response envelope, error model, exit-code mapping, and guide document schema.
- [ ] Wire the Typer application and implement `guide`, `init`, and `status`.
- [ ] Add test coverage for the envelope contract and bootstrap commands.
- [ ] Verify `uv sync`, `uv build`, `uv run pytest --tb=short`, `uv run ruff check src/ tests/`, and `uv run pyright src/`.

## Surprises & Discoveries

No discoveries yet - this section will be populated during implementation.

## Decision Log

- Decision: Use a `src/` layout with `hatchling`, with the package version defined in `src/cwmem/__init__.py` and loaded dynamically by `pyproject.toml`.
  Rationale: This matches the required packaging contract and keeps the import path and build metadata aligned.
  Source: PRD Sections 22.2 and 23.

- Decision: Every command writes exactly one structured JSON envelope to stdout, while progress and diagnostics go to stderr only.
  Rationale: The CLI is agent-first, and this output split is the core machine contract.
  Source: PRD Sections 13.1, 13.6, and 20.3.

- Decision: The bootstrap phase creates the full directory skeleton, including `.cwmem/`, `memory/`, and `models/model2vec/`, even though most domain behavior arrives in later phases.
  Rationale: Later phases should extend stable paths rather than inventing them repeatedly.
  Source: PRD Sections 12.1, 17.4, and 23.

- Decision: Canonical command IDs in the envelope use dotted names such as `system.guide`, `system.init`, `system.status`, `memory.add`, and `memory.search`.
  Rationale: Human command names may stay short, but the machine contract needs stable identifiers from day one.
  Source: PRD Section 13.2.

## Outcomes & Retrospective

To be completed at major milestones and at plan completion.

## Context and Orientation

The repository currently contains `PRD.md` and `.github/copilot-instructions.md`, but it does not yet contain the Python package scaffold, the test suite, or build metadata. This phase creates the first runnable version of the project so later phases can extend a real package instead of a design-only repo.

The package root is `src/cwmem/`. The command entry point is `src/cwmem/__main__.py`, and the Typer command wiring lives under `src/cwmem/cli/`. Shared output code belongs under `src/cwmem/output/`. Runtime state lives under `.cwmem/`, which is local-only and should be gitignored. Git-tracked collaboration artifacts live under `memory/`, which must already exist after `cwmem init` so future phases can export into a stable tree.

The phrase "envelope" means the single top-level JSON object returned by every command. It must always contain `schema_version`, `request_id`, `ok`, `command`, `result`, `warnings`, `errors`, and `metrics`. The phrase "guide document" means a machine-readable description of the CLI itself: commands, flags, schemas, error codes, exit codes, workflows, and storage rules.

## Plan of Work

Create `pyproject.toml` with the package metadata for `cwmem`, the `hatchling` build backend, and the CLI entry point `cwmem = "cwmem.__main__:main"`. Add `.gitignore` entries for `.cwmem/memory.sqlite`, `.cwmem/memory.sqlite.lock`, `.cwmem/logs/`, local virtual environments, and build artifacts. Add minimal `README.md`, `LICENSE`, and `AGENTS.md` files so the repository can build cleanly before later documentation phases expand them.

Create `src/cwmem/__init__.py` with `__version__`, and create `src/cwmem/__main__.py` with the root Typer application plus shared error-to-exit-code handling. Create the planned CLI modules `src/cwmem/cli/setup.py`, `src/cwmem/cli/read.py`, `src/cwmem/cli/write.py`, `src/cwmem/cli/graph.py`, `src/cwmem/cli/sync.py`, and `src/cwmem/cli/maintenance.py`. In this phase, only `guide`, `init`, and `status` are fully implemented; the other modules should still register placeholder commands that fail with a stable not-implemented error envelope instead of crashing.

Create `src/cwmem/core/models.py` for Pydantic models that describe the envelope, command errors, guide output, and status/init results. Create `src/cwmem/output/envelope.py`, `src/cwmem/output/json.py`, and `src/cwmem/output/table.py` so command handlers return typed domain results and a single formatter turns them into stdout output.

Implement `system.guide` so it exposes the command catalog, argument schemas, output schemas, error codes, exit codes, output precedence, concurrency policy, and storage layout. Implement `system.init` so it creates `.cwmem/`, `.cwmem/logs/`, `memory/entries/`, `memory/events/`, `memory/graph/`, `memory/taxonomy/`, `memory/manifests/`, and `models/model2vec/`, plus taxonomy seed files at `memory/taxonomy/tags.json`, `memory/taxonomy/relation-types.json`, and `memory/taxonomy/entity-types.json`. Implement `system.status` so it reports whether initialization has happened, where the main directories are, and which optional surfaces are still empty.

Add tests in `tests/test_envelope.py`, `tests/test_guide.py`, and `tests/test_setup_commands.py`. Use Typer's test runner in a temporary directory so the tests assert filesystem effects and the exact envelope keys without depending on the developer's real workspace.

## Concrete Steps

1. Create the package and repository scaffold.

   Edit `pyproject.toml`, `.gitignore`, `README.md`, `LICENSE`, and `AGENTS.md`. Create the directory tree `src/cwmem/`, `src/cwmem/cli/`, `src/cwmem/core/`, `src/cwmem/output/`, and `tests/`.

   The dependency set in `pyproject.toml` must include `typer`, `pydantic`, `orjson`, `numpy`, and `model2vec`, plus development tooling for `pytest`, `ruff`, and `pyright`.

2. Implement the envelope and command metadata layer.

   Add typed models in `src/cwmem/core/models.py` and helpers in `src/cwmem/output/envelope.py` that build the final envelope from command results and errors. Define the stable exit-code mapping `0`, `10`, `20`, `40`, `50`, and `90` now, even though most error variants arrive in later phases.

3. Wire the root CLI.

   In `src/cwmem/__main__.py`, build the root Typer app, register the setup/read/write/graph/sync/maintenance subcommands, and ensure unhandled exceptions are rendered as `ERR_INTERNAL_*` envelopes instead of raw tracebacks on stdout. Put only diagnostics on stderr.

4. Implement `guide`, `init`, and `status`.

   `guide` should return a machine-readable document that already lists the future command surface, with each command marked as implemented or planned. `init` must create the runtime and checked-in directory structure idempotently. `status` must report path existence, package version, and whether the runtime database file exists yet.

5. Add test coverage.

   Write tests that assert the envelope always contains the required top-level keys, that `cwmem guide` includes command IDs and error codes, that `cwmem init` can be run twice safely, and that `cwmem status` reports an uninitialized repo before `init` and an initialized repo after it.

6. Run the standard project commands from the repository root.

    uv sync
    uv run pytest --tb=short
    uv run ruff check src/ tests/
    uv run pyright src/
    uv build
    uv run cwmem guide
    uv run cwmem init
    uv run cwmem status

   Expected: the build succeeds, the tests pass, `guide` returns `ok: true`, `init` creates the expected directories, and `status` reports `initialized: true` after initialization.

## Validation and Acceptance

From the repository root, run:

    uv run cwmem guide

Expected behavior: stdout is one JSON object whose `command` is `system.guide`; `result.command_catalog` includes at least `guide`, `init`, `status`, `add`, `update`, `search`, `sync export`, and `verify`; `warnings` and `errors` are arrays.

Then run:

    uv run cwmem init
    uv run cwmem status

Expected behavior: `init` returns the created paths in `result.created`, and `status` returns `initialized: true` plus existing paths for `.cwmem`, `memory`, and `models/model2vec`.

Finally run:

    uv run pytest --tb=short
    uv run ruff check src/ tests/
    uv run pyright src/
    uv build

Expected behavior: all checks pass. If any fail, treat that as incomplete work; do not move on to the next phase.

## Idempotence and Recovery

`cwmem init` must be safe to re-run. Use `mkdir(..., exist_ok=True)` and `CREATE TABLE IF NOT EXISTS` for any bootstrap storage. If `uv sync` or `uv build` fails halfway through, rerun the same command after fixing the reported issue; neither command should require manual cleanup beyond removing a broken local virtual environment.

Do not delete `.cwmem/` during retries unless this phase is still the only phase completed and there is no user data worth preserving. Once later phases exist, treat `.cwmem/memory.sqlite` as stateful user data.

## Artifacts and Notes

A successful `cwmem status` response should resemble:

    {
      "schema_version": "1.0",
      "ok": true,
      "command": "system.status",
      "target": {"resource": "repository"},
      "result": {
        "initialized": true,
        "package_version": "0.1.0",
        "paths": {
          "runtime_dir": ".cwmem",
          "memory_dir": "memory",
          "model_dir": "models/model2vec"
        }
      },
      "warnings": [],
      "errors": [],
      "metrics": {"duration_ms": 12}
    }

## Interfaces and Dependencies

Use Python 3.12+, `typer`, `pydantic` v2, `orjson`, `numpy`, and `model2vec`. The core interfaces that must exist at the end of this phase are `cwmem.__main__.main() -> None`, `cwmem.output.envelope.build_envelope(...) -> dict`, `cwmem.cli.setup.guide_command(...)`, `cwmem.cli.setup.init_command(...)`, and `cwmem.cli.setup.status_command(...)`.

`cwmem.core.models` must define typed models for `Envelope`, `CommandError`, `GuideDocument`, `StatusResult`, and `InitResult`. The guide result must include stable command IDs, exit-code mappings, error-code catalog entries, concurrency policy text, and storage-layout descriptions, because later phases rely on the CLI being self-describing.
