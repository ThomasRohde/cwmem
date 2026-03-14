# cwmem

`cwmem` is a repo-native institutional memory CLI for Enterprise Architecture work.

## Phase 1 scaffold

This repository now includes the initial runnable Python package scaffold for:

- `cwmem guide`
- `cwmem init`
- `cwmem status`

Future commands are present as stable placeholders that return structured error envelopes instead of crashing.

## Local workflow

```bash
uv sync
uv run cwmem guide
uv run cwmem init
uv run cwmem status
```

## Output contract

Every command writes exactly one JSON envelope to stdout. Diagnostics belong on stderr.

