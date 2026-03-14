# Copilot instructions for `cwmem`

This repository is currently **PRD-first**: `PRD.md` is the source of truth, and the planned `src/`, `tests/`, and workflow files are not scaffolded yet. Future Copilot sessions should anchor implementation decisions in `PRD.md`, especially sections 7, 8, 9, 11, 13, 18, 19, 22, 23, and 27.

## Build, test, and lint commands

There are no runnable build, test, or lint commands checked into the repository yet because the project scaffold is not present. The PRD standardizes the commands the implementation should use once `pyproject.toml`, `src/`, and `tests/` exist:

- `uv sync`
- `uv build`
- `uv run pytest --tb=short`
- `uv run pytest tests/<path_to_test>.py::test_name`
- `uv run ruff check src/ tests/`
- `uv run pyright src/`

Keep these exact tool choices unless the repository adds real config files that supersede the PRD.

## High-level architecture

`cwmem` is planned as a **repo-native institutional memory CLI**, not a server. The core split is:

- **Runtime state in SQLite** at `.cwmem/memory.sqlite` for operational queries, FTS5 search, graph storage, idempotency metadata, and rebuild/verification workflows.
- **Deterministic Git-tracked artifacts** under `memory/` for review, sharing, and recovery. SQLite is the operational store; `memory/**` is the collaboration surface.

The planned package layout is deliberately layered:

- `src/cwmem/cli/` for command entrypoints and CLI adapters
- `src/cwmem/core/` for domain logic, storage, search, graph, sync, validation, planning, and locking
- `src/cwmem/output/` for the structured response envelope and output rendering

Search is a three-part pipeline:

1. SQLite FTS5 BM25 lexical retrieval
2. local Model2Vec semantic retrieval
3. optional graph-aware expansion/reranking

The merged result set should use reciprocal-rank fusion or a documented equivalent. For v1, embeddings are stored in SQLite and cosine similarity is computed in Python/Numpy rather than relying on a native SQLite vector extension.

The knowledge graph is a first-class feature, not a sidecar. Nodes cover memory entries, events, entities, tags, and external references. Edges must carry provenance and confidence so graph expansion stays explainable.

The formal log is append-only and complements narrative memory. Corrections should produce follow-up events rather than destructive rewrites unless an explicit maintenance workflow says otherwise.

The CLI surface is designed around:

- **read commands** such as `guide`, `status`, `get`, `list`, `search`, `related`, `log`, `graph`, and `stats`
- **write commands** such as `init`, `add`, `update`, `deprecate`, `link`, `tag-add`, `tag-remove`, `event-add`, `entity-add`, `sync import`, `sync export`, and `build`
- **workflow commands** for risky operations: `plan`, `validate`, `apply`, and `verify`

## Key conventions

Every command must follow the CLI-MANIFEST-style envelope contract from the PRD:

- stdout returns one structured top-level envelope
- stderr is reserved for diagnostics, warnings, and progress
- canonical dotted command IDs belong in the envelope even if human-facing aliases exist
- stable error codes and stable category-based exit codes are part of the contract

Mutation safety is a core design constraint:

- every mutating command supports `--dry-run`
- retried write operations support `--idempotency-key`
- update/apply flows use fingerprints, including `--expected-fingerprint` and `--fail-on-drift`
- risky workflows follow `plan -> validate -> apply -> verify`

Concurrency rules are explicit and must not be weakened:

- writes acquire an exclusive sidecar lock at `.cwmem/memory.sqlite.lock`
- reads may run in parallel
- writes against the same database may not run in parallel
- lock failures should surface `ERR_LOCK_HELD` with lock-owner details and retry guidance

Determinism is a repository-level requirement, not an implementation detail:

- exported files must have stable filenames, stable ordering, canonical JSON serialization, and preserved timestamps
- narrative memory is expected to be one entry per file under `memory/entries/`
- formal events are append-only by default
- round-trip behavior between SQLite and exported artifacts must stay reproducible

When scaffolding the implementation, keep the planned stack and packaging conventions intact:

- Python 3.12+
- `typer`, `pydantic` v2, stdlib `sqlite3`, `orjson`, `numpy`, `model2vec`, optional `portalocker`
- `src/cwmem` layout with the version sourced from `src/cwmem/__init__.py`
- `hatchling` build backend
- CLI entry point `cwmem = "cwmem.__main__:main"`

Release automation is also part of the contract:

- the package name is `cwmem`
- the repository is `ThomasRohde/cwmem`
- planned workflows are `.github/workflows/ci.yml` and `.github/workflows/publish.yml`
- PyPI publishing uses Trusted Publisher / OIDC with environment `pypi`
- the pending publisher values already configured in PyPI must match exactly: owner `ThomasRohde`, repository `cwmem`, workflow `publish.yml`, environment `pypi`

If future sessions add code that conflicts with the PRD, prefer the checked-in implementation only when the newer source files clearly supersede the design contract; otherwise, preserve the PRD-defined behavior.
