# cwmem

`cwmem` is a repo-native institutional memory CLI for Enterprise Architecture work.

It keeps operational state in SQLite, exports deterministic reviewable artifacts under `memory/`, and exposes a machine-first CLI contract so humans and coding agents can use the same tool safely.

## Current feature set

- entry CRUD with automatic lifecycle events
- tags, formal events, and entity/edge graph workflows
- lexical, semantic, hybrid, and graph-expanded search
- deterministic `sync export` / `sync import`
- dry-run, idempotency keys, sidecar write locking, `plan`, `validate`, `apply`, and `verify`

## Local workflow

```bash
uv sync
uv run cwmem init
uv run cwmem add --title "Architecture decision" --type decision "Capture the rationale."
uv run cwmem search "architecture decision"
uv run cwmem sync export
uv run cwmem verify
```

## Safety contract

Every command writes exactly one JSON envelope to stdout.

Reads stay parallel-safe. Mutating commands serialize through `.cwmem/memory.sqlite.lock` and support the safety flags below where relevant:

- `--dry-run`
- `--idempotency-key`
- `--wait-lock`
- `--plan-out`

High-risk workflows follow:

```bash
uv run cwmem plan sync-export --plan-out .cwmem/plans/export-plan.json
uv run cwmem validate --plan .cwmem/plans/export-plan.json
uv run cwmem apply --plan .cwmem/plans/export-plan.json
uv run cwmem verify
```

## Deterministic sync surface

Tracked collaboration artifacts live under:

- `memory/entries/`
- `memory/events/`
- `memory/graph/`
- `memory/taxonomy/`
- `memory/manifests/`

Use `uv run cwmem sync export --check` in CI or before commit to confirm the checked-in export tree matches the runtime database.

## Local quality gate

```bash
uv run ruff check src tests
uv run pyright src
uv run pytest --tb=short
uv build
```

## Release automation

- CI workflow: `.github/workflows/ci.yml`
- Publish workflow: `.github/workflows/publish.yml`
- Contributor guide: `CONTRIBUTING.md`
- Agent expectations: `AGENTS.md`

The publish workflow is designed for GitHub OIDC + PyPI Trusted Publisher with the `pypi` environment and `publish.yml` workflow binding.
