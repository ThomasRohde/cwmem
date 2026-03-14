# Agent notes for `cwmem`

## Phase 1 boundaries

- Keep the CLI machine-first: one JSON envelope on stdout, diagnostics on stderr.
- Implement `guide`, `init`, and `status` first.
- Keep future command surfaces discoverable in `cwmem guide`, even if they are placeholders.
- Avoid editing `tests/**` during scaffold work unless a later task explicitly requires a shared fixture.

## Expected local commands

- `uv sync`
- `uv build`
- `uv run pytest --tb=short`
- `uv run ruff check src/ tests/`
- `uv run pyright src/`

