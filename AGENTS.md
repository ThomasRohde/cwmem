# Agent notes for `cwmem`

## Runtime contract

- Keep the CLI machine-first: one JSON envelope on stdout, diagnostics on stderr.
- Prefer safety-aware writes: `--dry-run`, `--idempotency-key`, and `--wait-lock`.
- Reads may run in parallel; writes must serialize through `.cwmem/memory.sqlite.lock`.
- Treat checked-in `memory/` artifacts as generated output; update them with `cwmem sync export`, not manual edits.

## Preferred workflows

- safe export review:
  - `uv run cwmem sync export`
  - `uv run cwmem sync export --check`
  - `uv run cwmem verify`
- higher-risk apply flow:
  - `uv run cwmem plan sync-export --plan-out .cwmem/plans/export-plan.json`
  - `uv run cwmem validate --plan .cwmem/plans/export-plan.json`
  - `uv run cwmem apply --plan .cwmem/plans/export-plan.json`
  - `uv run cwmem verify`

## Expected local commands

- `uv sync`
- `uv build`
- `uv run pytest --tb=short`
- `uv run ruff check src tests`
- `uv run pyright src`

