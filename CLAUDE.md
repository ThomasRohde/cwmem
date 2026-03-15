# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is cwmem

Repo-native institutional memory CLI for Enterprise Architecture. Keeps fast operational state in SQLite (`.cwmem/`) while exporting deterministic collaboration artifacts to a checked-in `memory/` directory. Designed for both humans and coding agents.

## Commands

```bash
# Setup
uv sync

# Local quality gate (run before PRs)
uv run ruff check src tests
uv run pyright src
uv run pytest --tb=short
uv build

# Run a single test
uv run pytest tests/test_foo.py -k "test_name" --tb=short

# Format (ruff auto-fix)
uv run ruff check --fix src tests
```

## Architecture

**Data flow:** CLI command → `cli/*.py` handler → `core/store.py` (SQLite CRUD) → JSON envelope on stdout.

**Dual-view system:**
- `.cwmem/memory.sqlite` — runtime state, fast queries
- `memory/` — checked-in JSONL/markdown artifacts for version control and PR review
- Database rebuilds from artifacts via `cwmem sync import`; artifacts regenerate via `cwmem sync export`

**Key modules in `src/cwmem/`:**
- `core/models.py` — all Pydantic models (EntryRecord, EventRecord, EntityRecord, EdgeRecord, inputs, outputs)
- `core/store.py` — SQLite CRUD, schema, the central data layer (~1350 lines)
- `core/hybrid_search.py` — Reciprocal Rank Fusion merging FTS5 lexical + Model2Vec semantic search
- `core/graph.py` — directed edge operations, depth-limited traversal
- `core/safety.py` — idempotency, dry-run, mutation safety
- `cli/` — one file per command group: `read.py`, `write.py`, `sync.py`, `graph.py`, `setup.py`, `maintenance.py`
- `output/envelope.py` — JSON envelope protocol (every command returns `{ok, command, result, warnings, errors}`)
- `ui/services.py` + `ui/view_models.py` — shared UI service layer (used by TUI, designed for reuse)
- `tui/app.py` — Textual-based terminal UI

**Embedding model:** Vendored Model2Vec in `models/model2vec/`, lazy-loaded on `cwmem build`.

## Key conventions

- **Machine-first output:** every CLI command returns a single JSON envelope on stdout; diagnostics go to stderr. Exception: `cwmem tui` launches a Textual app.
- **Safety flags:** prefer `--dry-run` before mutations, `--idempotency-key` for agent-retried writes, `--wait-lock` for concurrent access.
- **Write serialization:** reads are parallel-safe; writes serialize through `.cwmem/memory.sqlite.lock` (portalocker).
- **Generated artifacts:** never hand-edit files under `memory/`; use `cwmem sync export` to regenerate them.
- **Version source:** `src/cwmem/__init__.py` (single `__version__` string, read by hatchling).

## Code style

- Python ≥3.12, line length 100
- Ruff rules: E, F, I, UP, B
- Pyright standard mode, type annotations expected on public APIs
- Pydantic v2 for all data models, orjson for serialization

## Release process

1. Update `CHANGELOG.md`
2. Bump version in `src/cwmem/__init__.py`
3. Run full quality gate
4. `uv build && python -m pip install --force-reinstall dist/*.whl` (smoke test)
5. Push to `master` → `publish.yml` publishes to PyPI via GitHub Trusted Publisher
