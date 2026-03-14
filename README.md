# cwmem

[![PyPI version](https://img.shields.io/pypi/v/cwmem)](https://pypi.org/project/cwmem/)
[![Python 3.12+](https://img.shields.io/pypi/pyversions/cwmem)](https://pypi.org/project/cwmem/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

`cwmem` is a repo-native institutional memory CLI for Enterprise Architecture work.

It keeps fast operational state in SQLite, exports deterministic collaboration artifacts under `memory/`, and gives both humans and coding agents a consistent way to capture decisions, events, entities, and graph links inside a repository.

## Who it is for

- **AI coding agents** that need a stable, scriptable memory layer next to the code they change
- **Enterprise architects** who want architecture decisions, milestones, and relationships stored in the repo
- **Platform and delivery teams** who need search, reviewable exports, and a shared institutional memory

## What `cwmem` gives you

- entry CRUD with automatic lifecycle events
- tags, formal events, and entity / edge graph workflows
- lexical, semantic, hybrid, and graph-expanded retrieval
- deterministic `sync export` / `sync import` for checked-in artifacts
- dry-run, idempotency keys, sidecar locking, `plan`, `validate`, `apply`, and `verify`
- a machine-first JSON-envelope CLI with human-readable help and version output
- a Textual-based human explorer via `cwmem tui`, including safe add / tag / link workflows

## Installation

With `pip`:

```bash
pip install cwmem
```

With [`uv`](https://docs.astral.sh/uv/):

```bash
uv tool install cwmem
```

Check the installed version:

```bash
cwmem --version
```

## Quick start

### POSIX shells

```bash
# Initialize the repository memory surfaces
cwmem init

# Capture a decision or note
cwmem add --title "Adopt repo-native memory" --type decision \
  "Store architectural context alongside the codebase."

# Or pipe a plain-text body explicitly
printf 'Store architectural context alongside the codebase.' | \
  cwmem add --title "Adopt repo-native memory" --type decision --body-from-stdin

# Search and inspect what you stored
cwmem search "repo-native memory"
cwmem list

# Or explore it interactively as a human
cwmem tui

# Add structure with entities and graph edges
cwmem entity-add --entity-type system --name "cwmem"
cwmem link mem-000001 ent-000001 --relation references

# Refresh derived state when needed, then export and verify consistency
cwmem build
cwmem sync export
cwmem sync export --check
cwmem verify
```

### PowerShell

```powershell
# Initialize repository memory surfaces
cwmem init

# Capture a decision
cwmem add --title "Adopt repo-native memory" --type decision `
  "Store architectural context alongside the codebase."

# Or pipe a plain-text body explicitly
Get-Content .\note.txt -Raw | `
  cwmem add --title "Imported note" --type note --body-from-stdin

# Read JSON envelopes naturally in PowerShell
cwmem search "repo-native memory" | ConvertFrom-Json

# Refresh derived state when needed, then export and verify
cwmem build
cwmem sync export
cwmem verify
```

Without `--body-from-stdin`, piped stdin is reserved for JSON object input when
`cwmem add` is driven machine-to-machine.

## Interactive TUI

`cwmem tui` launches a Textual interface for humans who want to browse and
work with repository memory without dropping into one command at a time.

The current TUI includes:

- a repository status dashboard
- entry browsing and preview
- lexical / semantic / hybrid search with graph expansion
- related / graph inspection
- formal log browsing
- preview / apply flows for `add`, `tag`, and `link`

Useful shortcuts:

- `Ctrl+P` opens the command palette
- `F1` through `F6` switch between the main tabs
- `Ctrl+R` refreshes the active tab

`cwmem tui` is intentionally human-only. It requires an interactive TTY and
returns a structured validation error instead of launching when invoked from a
non-interactive context. An ambient `LLM=true` environment does not block an
explicit human TTY launch.

The app is built on a shared `cwmem.ui` service/view-model layer so a later
browser-facing `cwmem gui` can reuse the same exploration logic.

## How `cwmem` fits into a repository

`cwmem` keeps two views of the same memory system:

- **runtime state** in `.cwmem/` for SQLite, indexes, lock files, and generated plans
- **tracked collaboration artifacts** in `memory/` for review, sync, and git history

The main tracked surfaces are:

- `memory/entries/`
- `memory/events/`
- `memory/graph/`
- `memory/taxonomy/`
- `memory/manifests/`

This split gives you fast local operations without giving up reviewable, deterministic files in version control.

## Core workflow

For everyday memory capture:

```bash
cwmem init
cwmem add --title "Architecture decision" --type decision "Capture the rationale."
cwmem event-add --event-type milestone "MVP shipped"
cwmem search "architecture decision"
cwmem related mem-000001
cwmem build
cwmem sync export
cwmem verify
```

After mutations that affect derived search state or tracked artifacts, the common
safe path is `cwmem build`, then `cwmem sync export`, then `cwmem verify`.

For higher-risk workflows that should be reviewed before mutating state:

```bash
cwmem plan sync-import --plan-out .cwmem/plans/import-plan.json
cwmem validate --plan .cwmem/plans/import-plan.json
cwmem apply --plan .cwmem/plans/import-plan.json
cwmem verify
```

## Safety model

Every command writes exactly one JSON envelope to stdout. That makes the CLI easy to automate, inspect, and pipe into other tooling.

The deliberate exception is `cwmem tui`: on successful launch it takes over the
terminal as an interactive Textual app, and on non-interactive launch attempts
it returns a normal structured validation envelope instead.

Reads are parallel-safe. Mutating commands serialize through `.cwmem/memory.sqlite.lock` and support safety flags such as:

- `--dry-run`
- `--idempotency-key`
- `--wait-lock`
- `--plan-out`

Use `cwmem guide` when you want the machine-readable command catalog, schema information, and workflow contract.

## Command groups

| Command | What it is for |
|---------|-----------------|
| `cwmem guide` | Machine-readable CLI contract and workflow metadata |
| `cwmem init` / `status` | Bootstrap and inspect repository memory surfaces |
| `cwmem tui` | Human-first Textual explorer with dashboard, search, graph, log, and safe add / tag / link flows |
| `cwmem add`, `update`, `tag-add`, `event-add`, `entity-add`, `link` | Capture or mutate memory records |
| `cwmem get`, `list`, `search`, `related`, `graph`, `log` | Read, retrieve, search, and traverse memory |
| `cwmem sync export` / `sync import` | Move between SQLite runtime state and checked-in artifacts |
| `cwmem build`, `stats`, `validate`, `plan`, `apply`, `verify` | Rebuild derived data, inspect health, and run safe workflows |

## Deterministic collaboration surface

`cwmem sync export` writes a deterministic `memory/` tree so that:

- pull requests can review memory changes like code changes
- the runtime database can be reconstructed from tracked artifacts
- CI can detect drift with `cwmem sync export --check`

This makes architecture memory auditable rather than hidden in a local database.

## Local quality gate

Run this before opening a PR or cutting a release:

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

PyPI publishing uses GitHub OIDC Trusted Publisher with the `pypi` environment and publishes automatically on pushes to `master`.

## Repository docs

- `README.md` — product overview and quick start
- `CONTRIBUTING.md` — local development and release checklist
- `AGENTS.md` — agent expectations and workflow conventions

If you want the CLI to explain itself interactively, start with:

```bash
cwmem --help
cwmem guide
```
