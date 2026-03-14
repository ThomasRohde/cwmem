# Contributing to `cwmem`

## Setup

```bash
uv sync
uv run cwmem guide
uv run cwmem init
```

## Development rules

- keep the CLI machine-first: one JSON envelope on stdout
- prefer `--dry-run` before risky mutations
- use `--idempotency-key` for agent-retried writes
- do not hand-edit generated `memory/entries/*.md` or JSONL artifacts; regenerate them with `cwmem sync export`

## Local quality gate

Run this before opening a PR:

```bash
uv run ruff check src tests
uv run pyright src
uv run pytest --tb=short
uv build
```

## Memory workflow

Typical reviewable change flow:

```bash
uv run cwmem add --dry-run --title "..." "..."
uv run cwmem add --title "..." "..."
uv run cwmem sync export
uv run cwmem sync export --check
uv run cwmem verify
```

For high-risk sync workflows:

```bash
uv run cwmem plan sync-import --plan-out .cwmem/plans/import-plan.json
uv run cwmem validate --plan .cwmem/plans/import-plan.json
uv run cwmem apply --plan .cwmem/plans/import-plan.json
uv run cwmem verify
```

## Pull requests

- summarize memory-impacting changes
- mention whether export artifacts changed
- note any new safety flags, workflow semantics, or release behavior
- include the local gate output when practical

## Release checklist

1. Update `CHANGELOG.md`.
2. Bump the package version in `src/cwmem/__init__.py`.
3. Run the full local quality gate.
4. Run `python -m pip install --force-reinstall dist/*.whl` after `uv build`.
5. Create or publish a GitHub release to trigger `.github/workflows/publish.yml`.

PyPI publishing is configured for GitHub Trusted Publisher with workflow `publish.yml` and environment `pypi`.
