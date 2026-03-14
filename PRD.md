# Coworker Memory CLI (`cwmem`) — Product Requirements Document

Version: 0.1  
Status: Draft  
Audience: EA Coworker maintainers, implementation agents, reviewers  
Primary implementation stack: Python 3.12+, SQLite, Model2Vec, Typer, Pydantic v2

---

## 1. Executive summary

The Coworker Memory CLI is a repo-native institutional memory system for Enterprise Architecture work. It gives the Coworker repository a durable shared memory layer that:

- stores architecture decisions, findings, insights, references, and formal log events
- supports hybrid retrieval with SQLite FTS5 BM25 and local semantic embeddings
- maintains an explicit knowledge graph of entities and relationships
- exports deterministic, git-friendly artifacts for review, sharing, and recovery
- follows an agent-first CLI contract so coding agents can use it safely and reliably

The product is designed for a team that works inside Git, wants a local/offline-first workflow, and needs a memory system that can be consumed both by humans and by agents.

The CLI must be suitable for daily EA work, not just experimentation. That means:

- stable machine-readable outputs
- explicit read/write separation
- safe mutation workflows
- deterministic export/import behavior
- concurrency rules for multi-agent use
- a lightweight semantic search stack that can live inside the repo

This PRD deliberately builds on two proven inputs:

1. the ArchGuard pattern already validated in your repo: JSONL/repo artifacts + SQLite FTS5 + Model2Vec + hybrid search + reciprocal-rank fusion
2. the CLI-MANIFEST standard for agent-first CLIs: one structured response envelope, stable error codes and exit codes, guide-driven discoverability, stdout/stderr discipline, dry-run semantics, plan/validate/apply/verify workflows, and documented locking/concurrency rules

---

## 2. Problem statement

EA work produces high-value knowledge, but that knowledge is fragmented across:

- chat threads
- pull requests
- architecture notes
- ad hoc markdown files
- meeting notes
- rejected AI outputs
- decisions captured too late or not captured at all

This causes the same problems repeatedly:

- decisions are forgotten
- terminology drifts
- rationale is lost
- prior work is hard to discover semantically
- agents have no stable memory substrate to reason over
- the team lacks a formal log that is both human-readable and machine-queryable

The Coworker repo needs a persistent memory layer that is:

- local and shareable
- repo-native
- searchable by both keywords and meaning
- linkable as a graph
- exportable into deterministic files that can be checked into Git
- operable from a CLI that agents can trust

---

## 3. Product goals

### 3.1 Primary goals

1. Create persistent shared memory for the Coworker repo.
2. Support hybrid retrieval: exact/lexical plus semantic similarity.
3. Support explicit tagging and a formal append-only event log.
4. Support a knowledge graph for entities and relationships.
5. Keep the solution lightweight, local, and repo-portable.
6. Make the CLI agent-first and CLI-MANIFEST-compliant.
7. Make SQLite operationally useful while still generating deterministic git-checkable artifacts.

### 3.2 Secondary goals

1. Make memory reviewable in pull requests.
2. Make it easy to reconstruct the local database from checked-in artifacts.
3. Enable future MCP/server wrappers without changing the core domain model.
4. Enable later automation such as auto-tagging, relation extraction, and “learn from PR/rejection”.

### 3.3 Non-goals for v1

1. Real-time collaborative server mode.
2. Cloud-hosted vector search.
3. Large-scale distributed graph database.
4. Full natural-language autonomous extraction from every repo artifact.
5. Full-text indexing of arbitrary binaries.
6. Fine-grained permissions or multi-tenant auth.

---

## 4. Users and usage modes

### 4.1 Primary users

- Enterprise architects working in the Coworker repo
- Architecture copilots and coding agents
- Maintainers reviewing architecture memory changes in pull requests

### 4.2 Usage modes

#### Human interactive mode

A human runs `cwmem` from a terminal to:

- add memory
- search prior decisions
- inspect related items
- export reviewable files
- build or verify the local index

#### Agent mode

An agent runs `cwmem` non-interactively to:

- retrieve memory for current work
- add or patch memory records
- attach tags and relationships
- generate plans and dry-runs before mutations
- export deterministic artifacts for commit

#### CI/automation mode

Automation runs `cwmem` to:

- verify exports are up to date
- rebuild the local DB from checked-in artifacts
- validate graph integrity
- enforce schema and taxonomy rules

---

## 5. Product principles

### 5.1 Agent-first contract

Every command returns one stable JSON envelope on stdout. Human-friendly tables are optional output modes, not the contract.

### 5.2 Read/write separation

Read commands inspect. Write commands mutate. Names must make that obvious.

### 5.3 SQLite for operations, deterministic files for collaboration

SQLite is the runtime database and search engine. Deterministic exported files are the collaboration and review surface. The system must support round-tripping between both.

### 5.4 Hybrid retrieval by default

Keyword search alone is not enough for architecture memory. Semantic search alone is not enough for IDs, tags, and exact terminology. The system must combine both.

### 5.5 Explicit provenance

Every record, event, entity, and relationship must have traceable origin metadata.

### 5.6 Safe mutation

Every mutation must support preview, validation, and recoverability.

### 5.7 Offline-first and repo-portable

The core workflow must function offline and must not depend on hosted infrastructure.

---

## 6. Product scope

The CLI manages five first-class resource types.

### 6.1 Memory entries

Narrative memory items such as:

- decisions
- findings
- lessons learned
- standards notes
- meeting takeaways
- architecture insights
- rejected AI output worth preserving

### 6.2 Events

Append-only formal log items such as:

- decision recorded
- standard superseded
- model updated
- search corpus rebuilt
- relation asserted

### 6.3 Tags

Controlled or free-form labels used for filtering, reporting, grouping, and governance.

### 6.4 Entities

Named graph nodes such as:

- system
- capability
- domain
- standard
- technology
- team
- person
- repo artifact
- initiative

### 6.5 Relationships

Directed graph edges such as:

- depends_on
- influences
- supersedes
- related_to
- derived_from
- owned_by
- contradicts
- supports
- mentions

---

## 7. Core design decision: storage model

### 7.1 Runtime operational store

The local runtime store is SQLite.

SQLite is used for:

- FTS5 BM25 search
- normalized relational data
- event queries
- graph storage
- metadata joins
- operational consistency
- local rebuilds and verification

Default runtime database path:

```text
.cwmem/memory.sqlite
```

This file is gitignored by default.

### 7.2 Git-friendly collaboration artifacts

The system must export deterministic artifacts under a checked-in `memory/` tree.

Recommended layout:

```text
memory/
  entries/
    mem-000001.md
    mem-000002.md
  events/
    events.jsonl
  graph/
    nodes.jsonl
    edges.jsonl
  taxonomy/
    tags.json
    relation-types.json
    entity-types.json
  manifests/
    export-manifest.json
```

These exported files are the review and sharing surface in Git.

### 7.3 Round-trip requirement

The system must support both directions:

1. SQLite -> exported files (`sync export`)
2. exported files -> SQLite (`sync import` or `rebuild`)

This ensures:

- local runtime speed
- Git reviewability
- disaster recovery
- CI reproducibility
- easy onboarding on a new machine

### 7.4 Determinism requirement

Exports must be stable and reproducible.

That means:

- stable filename generation
- stable sorting
- canonical JSON serialization
- normalized whitespace rules
- no non-deterministic IDs during export
- timestamps preserved, not regenerated, unless explicitly requested

---

## 8. Search architecture

### 8.1 Hybrid retrieval model

Search uses three layers:

1. SQLite FTS5 BM25 lexical search
2. Model2Vec semantic similarity search
3. graph-aware expansion/reranking

The result set is merged using reciprocal-rank fusion (RRF) or a documented weighted equivalent.

### 8.2 BM25 layer

Use SQLite FTS5 for:

- titles
- body text
- tags
- entity names
- aliases
- IDs
- event messages

This layer handles:

- exact terminology
- identifiers
- acronyms
- narrow filters
- deterministic ranking for exact matches

### 8.3 Semantic layer

Use a vendored or repo-managed Model2Vec model for embeddings.

Requirements:

- model must be small enough to keep repo-portable
- inference must be local and CPU-friendly
- model files must be explicitly versioned
- embedding generation must be deterministic for a given model version

Recommended path:

```text
models/model2vec/
```

The semantic layer handles:

- synonymy
- paraphrase matching
- concept similarity
- “same idea, different words” retrieval

### 8.4 Vector storage

For v1, store embeddings in SQLite in a normalized table or compact blob representation, but compute cosine similarity in Python/Numpy.

Reason:

- simpler packaging
- no mandatory SQLite extension dependency
- easier cross-platform setup
- sufficient for expected EA-memory corpus sizes

Optional later optimization:

- sqlite-vec or other SQLite-native vector indexing

### 8.5 Reranking and graph expansion

After lexical + vector retrieval:

1. merge candidate sets
2. optionally expand via 1-hop graph relations
3. rerank with a documented scoring policy

Graph expansion must be conservative and explainable. Search results should indicate when a result was found via:

- lexical match
- semantic match
- graph expansion

### 8.6 Search filters

Search must support filters for:

- tag
- type
- author
- date range
- event type
- entity type
- relation type
- status
- related entity

---

## 9. Knowledge graph requirements

### 9.1 Purpose

The knowledge graph is not a separate product. It is a first-class memory capability.

It exists to:

- connect records semantically and structurally
- support “what is related to this?” workflows
- support graph-aware retrieval and explanation
- make architecture context navigable by agents

### 9.2 Graph node types

Minimum v1 node types:

- memory_entry
- event
- entity
- tag
- external_ref

Entity subtypes must include:

- system
- capability
- domain
- standard
- technology
- team
- person
- artifact
- initiative

### 9.3 Graph edge types

Minimum v1 relation types:

- related_to
- mentions
- depends_on
- influences
- derived_from
- supersedes
- contradicts
- owned_by
- supports
- affects

### 9.4 Relationship provenance

Every edge must capture provenance:

- explicit_user
- inferred_rule
- extracted_model
- imported

Every edge must also capture confidence or assertion strength.

### 9.5 Graph authoring modes

V1 must support three authoring modes:

1. explicit CLI relation commands
2. relation declarations on add/update payloads
3. deterministic import from exported graph files

Optional later mode:

4. model-assisted extraction with review

### 9.6 Graph query requirements

The CLI must support:

- list related nodes for a resource
- show subgraph around a node
- filter graph by relation type
- export graph as JSONL
- explain why two items are linked

---

## 10. Formal log requirements

### 10.1 Formal log purpose

The system must support an append-only formal log in addition to narrative memory.

The formal log exists to capture:

- notable changes
- architecture governance actions
- memory lifecycle events
- system operations that matter for audit/review

### 10.2 Event structure

Each event must include:

- event_id
- event_type
- timestamp
- actor
- summary
- body
- tags
- linked resources
- provenance

### 10.3 Append-only semantics

The exported event log is append-only by default.

Corrections should create follow-up events, not destructive rewrites, unless explicitly running a maintenance/admin correction workflow.

### 10.4 Event and memory interplay

A memory entry may optionally emit one or more events on create/update/deprecate/link.

Examples:

- `memory.entry.created`
- `memory.entry.updated`
- `graph.edge.created`
- `taxonomy.tag.added`
- `index.rebuilt`

---

## 11. CLI surface

Command name:

```text
cwmem
```

### 11.1 Top-level command groups

```text
cwmem guide
cwmem init
cwmem status

cwmem add
cwmem update
cwmem deprecate
cwmem link
cwmem tag-add
cwmem tag-remove
cwmem event-add
cwmem entity-add

cwmem get
cwmem list
cwmem search
cwmem related
cwmem log
cwmem graph
cwmem stats

cwmem build
cwmem validate
cwmem sync export
cwmem sync import
cwmem verify
```

### 11.2 Read commands

Read commands must never mutate runtime state except where explicitly documented cache/index warm-up is allowed and reported.

Read commands include:

- `guide`
- `status`
- `get`
- `list`
- `search`
- `related`
- `log`
- `graph`
- `stats`

### 11.3 Write commands

Write commands mutate memory state and must support safety controls.

Write commands include:

- `init`
- `add`
- `update`
- `deprecate`
- `link`
- `tag-add`
- `tag-remove`
- `event-add`
- `entity-add`
- `sync import`
- `sync export` (writes files even if it does not mutate logical memory)
- `build` when it writes/rebuilds operational indexes

### 11.4 Workflow commands

For higher-risk mutations and sync workflows, support:

- `plan`
- `validate`
- `apply`
- `verify`

V1 may scope this to `sync` and batch imports first.

---

## 12. Command semantics and examples

### 12.1 `cwmem init`

Initializes local runtime and checked-in scaffolding.

Creates:

- `.cwmem/`
- `memory/` tree
- taxonomy seed files
- optional vendored model location if absent

### 12.2 `cwmem add`

Adds a memory entry.

Input modes:

- inline text
- markdown file
- JSON on stdin

Options:

- `--title`
- `--type`
- `--tags`
- `--author`
- `--relate`
- `--entity`
- `--event`
- `--dry-run`
- `--idempotency-key`

### 12.3 `cwmem update <id>`

Patches a memory entry.

Must support fingerprint checks to prevent stale overwrites.

### 12.4 `cwmem search <query>`

Runs hybrid retrieval.

Options:

- `--tag`
- `--type`
- `--author`
- `--from`
- `--to`
- `--semantic-only`
- `--lexical-only`
- `--expand-graph`
- `--limit`

### 12.5 `cwmem log`

Reads formal log events.

Options:

- `--event-type`
- `--tag`
- `--resource`
- `--since`
- `--until`

### 12.6 `cwmem graph show <id>`

Returns a graph neighborhood.

Options:

- `--depth`
- `--relation`
- `--entity-type`
- `--include-provenance`

### 12.7 `cwmem sync export`

Writes deterministic git-friendly artifacts from SQLite.

Options:

- `--dry-run`
- `--check`
- `--output-dir`
- `--plan-out`

### 12.8 `cwmem sync import`

Rebuilds or updates SQLite from exported artifacts.

Options:

- `--dry-run`
- `--fail-on-drift`
- `--plan-out`
- `--idempotency-key`

### 12.9 `cwmem build`

Rebuilds search indexes, graph projections, and validation caches.

### 12.10 `cwmem validate`

Validates:

- schema correctness
- referential integrity
- taxonomy compliance
- duplicate/public ID invariants
- graph edge validity
- export determinism

### 12.11 `cwmem verify`

Asserts postconditions after apply/import/export workflows.

Examples:

- export matches DB fingerprint
- graph edge counts match manifest
- FTS row counts match entries table
- model version matches expected embedding metadata

---

## 13. CLI-MANIFEST compliance requirements

### 13.1 One structured response envelope

Every command must return one top-level JSON envelope.

Minimum envelope:

```json
{
  "schema_version": "1.0",
  "request_id": "req_20260314_120000_abcd1234",
  "ok": true,
  "command": "memory.search",
  "target": {"resource": "entries"},
  "result": {},
  "warnings": [],
  "errors": [],
  "metrics": {
    "duration_ms": 14
  }
}
```

Required invariants:

- `schema_version` always present
- `request_id` always present
- `ok` always present
- `command` always present
- `result` always present, even if `null`
- `warnings` always an array
- `errors` always an array
- `metrics` always present

### 13.2 Stable command IDs

Human commands may have aliases, but the envelope must use canonical dotted command IDs.

Examples:

- `memory.add`
- `memory.update`
- `memory.search`
- `memory.sync.export`
- `memory.graph.show`

### 13.3 Stable error codes

Errors must include:

- `code`
- `message`
- `retryable`
- `suggested_action`
- `details`

Minimum taxonomy:

- `ERR_VALIDATION_*`
- `ERR_CONFLICT_*`
- `ERR_IO_*`
- `ERR_AUTH_*`
- `ERR_LOCK_HELD`
- `ERR_INTERNAL_*`

### 13.4 Exit codes

Use stable category-based exit codes.

Recommended mapping:

- `0` success
- `10` validation
- `20` auth/permission
- `40` conflict/lock/fingerprint mismatch
- `50` I/O/storage
- `90` internal error

### 13.5 Guide command

`cwmem guide` must return machine-readable CLI documentation, including:

- command catalog
- input schemas
- output schemas
- error codes
- exit code mapping
- compatibility policy
- output-mode policy
- workflow commands
- concurrency rules
- identifier syntax

### 13.6 Output rules

- stdout: structured envelope only
- stderr: progress, diagnostics, warnings, debug events
- no decorative output on stdout
- support `isatty()` behavior
- support `LLM=true`
- explicit output precedence: flags > env vars > `isatty()` defaults

### 13.7 Verbosity model

Support at least:

- `--quiet`
- default
- `--verbose`

### 13.8 Dry-run on every mutation

Every mutating command must support `--dry-run` and return a structured change summary.

### 13.9 Plan/validate/apply/verify

For higher-risk workflows, plans must be first-class reviewable artifacts.

### 13.10 Locking and concurrency

Mutating commands must use exclusive locking and document safe parallelism.

### 13.11 Idempotency

Write commands that may be retried by agents must support `--idempotency-key`.

---

## 14. Data model

### 14.1 Entry model

Fields:

- `id` internal stable ID (ULID recommended)
- `public_id` user-facing ID (`mem-000001`)
- `title`
- `body`
- `type`
- `status`
- `author`
- `created_at`
- `updated_at`
- `source`
- `provenance`
- `tags[]`
- `related_ids[]`
- `entity_refs[]`
- `fingerprint`

### 14.2 Event model

Fields:

- `id`
- `public_id`
- `event_type`
- `summary`
- `body`
- `actor`
- `timestamp`
- `tags[]`
- `resource_refs[]`
- `provenance`

### 14.3 Entity model

Fields:

- `id`
- `public_id`
- `entity_type`
- `name`
- `description`
- `aliases[]`
- `tags[]`
- `status`
- `source`
- `fingerprint`

### 14.4 Edge model

Fields:

- `id`
- `source_id`
- `target_id`
- `relation_type`
- `direction`
- `confidence`
- `provenance`
- `created_at`
- `created_by`

---

## 15. SQLite schema

The precise schema may evolve, but v1 should include at least the following tables.

### 15.1 Core tables

```sql
CREATE TABLE entries (
  id TEXT PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  type TEXT NOT NULL,
  status TEXT NOT NULL,
  author TEXT,
  source TEXT,
  provenance TEXT,
  fingerprint TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE events (
  id TEXT PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  event_type TEXT NOT NULL,
  summary TEXT NOT NULL,
  body TEXT,
  actor TEXT,
  provenance TEXT,
  timestamp TEXT NOT NULL
);

CREATE TABLE entities (
  id TEXT PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  entity_type TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  source TEXT,
  provenance TEXT,
  fingerprint TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE edges (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  target_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  confidence REAL,
  provenance TEXT NOT NULL,
  created_at TEXT NOT NULL,
  created_by TEXT,
  UNIQUE(source_id, target_id, relation_type, provenance)
);
```

### 15.2 Mapping tables

```sql
CREATE TABLE entry_tags (
  entry_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  PRIMARY KEY (entry_id, tag)
);

CREATE TABLE event_tags (
  event_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  PRIMARY KEY (event_id, tag)
);

CREATE TABLE entity_tags (
  entity_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  PRIMARY KEY (entity_id, tag)
);

CREATE TABLE entry_entities (
  entry_id TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  PRIMARY KEY (entry_id, entity_id)
);

CREATE TABLE event_resources (
  event_id TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  PRIMARY KEY (event_id, resource_id)
);
```

### 15.3 Search tables

```sql
CREATE VIRTUAL TABLE entries_fts USING fts5(
  public_id,
  title,
  body,
  tags,
  tokenize = 'porter unicode61'
);

CREATE VIRTUAL TABLE events_fts USING fts5(
  public_id,
  event_type,
  summary,
  body,
  tags,
  tokenize = 'porter unicode61'
);

CREATE VIRTUAL TABLE entities_fts USING fts5(
  public_id,
  entity_type,
  name,
  description,
  aliases,
  tags,
  tokenize = 'porter unicode61'
);
```

### 15.4 Embedding tables

```sql
CREATE TABLE embeddings (
  resource_id TEXT PRIMARY KEY,
  resource_type TEXT NOT NULL,
  model_name TEXT NOT NULL,
  model_version TEXT NOT NULL,
  vector_dim INTEGER NOT NULL,
  vector_blob BLOB NOT NULL,
  content_fingerprint TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 15.5 Operational metadata

```sql
CREATE TABLE metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

Keys should include:

- `schema_version`
- `export_manifest_fingerprint`
- `embedding_model_name`
- `embedding_model_version`
- `last_build_at`
- `last_export_at`

---

## 16. Exported artifact formats

### 16.1 Entries

Human-readable markdown with YAML front matter.

Example:

```markdown
---
id: 01ARZ3NDEKTSV4RRFFQ69G5FAV
public_id: mem-000001
type: decision
status: active
author: thomas
created_at: 2026-03-14T10:10:00Z
updated_at: 2026-03-14T10:10:00Z
tags:
  - capability-model
  - governance
entity_refs:
  - ent-000014
related_ids:
  - mem-000003
fingerprint: sha256:...
---

# Capability model alignment

We aligned the EA capability model with the BCM baseline because...
```

### 16.2 Events

Append-only JSONL.

### 16.3 Graph

`nodes.jsonl` and `edges.jsonl`, sorted deterministically.

### 16.4 Export manifest

A manifest file must capture:

- export version
- source DB fingerprint
- counts by resource type
- file fingerprints
- model metadata
- generated_at

---

## 17. Sync and round-trip workflows

### 17.1 Export workflow

Goal: make DB state reviewable in Git.

Flow:

1. gather current SQLite state
2. normalize and sort resources
3. render markdown/JSONL artifacts
4. compute file fingerprints
5. write export manifest
6. optionally verify clean round-trip compatibility

### 17.2 Import workflow

Goal: reconstruct or update SQLite from repo artifacts.

Flow:

1. read export manifest and artifacts
2. validate schema and integrity
3. compute import plan
4. apply import or rebuild
5. rebuild FTS and embeddings as required
6. verify DB fingerprint / counts

### 17.3 Check workflow

`cwmem sync export --check` must fail if exported files are stale relative to SQLite.

### 17.4 Recommended Git policy

- checked in: `memory/**`, `models/model2vec/**` if vendored
- ignored: `.cwmem/memory.sqlite`, transient logs, temp plans unless explicitly committed

---

## 18. Safety and mutation workflows

### 18.1 Dry-run requirement

Every mutation returns:

- `dry_run: true`
- summary counts
- concrete proposed changes
- impacted resources

### 18.2 Fingerprinting

All mutable resources must have content fingerprints.

Update/apply workflows should support:

- `--expected-fingerprint`
- `--fail-on-drift`

### 18.3 Backups and snapshots

Before destructive maintenance operations, support:

- automatic DB backup
- optional export snapshot artifact

### 18.4 Apply/verify discipline

For risky operations such as bulk import or batch patch:

- `plan` produces a file artifact
- `validate` checks the plan against current state
- `apply` executes with optional `--dry-run`
- `verify` asserts postconditions

### 18.5 Idempotency

All write operations that agents may retry must accept `--idempotency-key`.

Minimum v1 requirement:

- store recent idempotency keys and resulting resource IDs in SQLite metadata or a dedicated table

---

## 19. Concurrency and locking

### 19.1 Exclusive lock

Mutating commands must acquire an exclusive sidecar lock.

Recommended lock path:

```text
.cwmem/memory.sqlite.lock
```

Lock metadata should include:

- PID
- hostname
- timestamp
- command
- request_id

### 19.2 Wait policy

Support:

- `--wait-lock <seconds>`

### 19.3 Safe concurrency rules

The CLI guide must state:

- reads may run in parallel
- writes to the same DB may not run in parallel
- batch workflows should serialize apply phases
- CI validation may run in parallel with reads but not writes unless using separate DB copies

### 19.4 Lock errors

Lock failures must return:

- code: `ERR_LOCK_HELD`
- retryability guidance
- lock owner details

---

## 20. Output modes and UX

### 20.1 Output formats

Supported formats:

- `json` (default contract)
- `table` (human convenience)
- `markdown` (report/export only where appropriate)

### 20.2 Precedence

Output-mode precedence must follow:

1. explicit flags
2. environment variables
3. `isatty()` defaults

### 20.3 LLM mode

Support `LLM=true` and make it effectively a no-surprises mode:

- JSON envelope on stdout
- minimal stderr noise
- no interactive prompts
- no decorative formatting

### 20.4 Logging

Long-running operations may write verbose logs to a file and return the path in the envelope.

---

## 21. Guide and discoverability

`cwmem guide` must return machine-readable documentation including:

- schema version
- compatibility policy
- command catalog
- arguments and flags
- examples
- error codes
- exit codes
- workflows
- concurrency policy
- storage layout
- import/export contract

This is not optional. Agents must be able to discover how to use the CLI from the CLI itself.

---

## 22. Tech stack and implementation constraints

### 22.1 Language and runtime

- Python 3.12+
- `typer`
- `pydantic` v2
- stdlib `sqlite3`
- `orjson`
- `numpy`
- `model2vec`
- optional `portalocker`

### 22.2 Packaging

- publish as the PyPI package `cwmem`
- repository of record: `https://github.com/ThomasRohde/cwmem`
- package author metadata should be `Thomas Klok Rohde <rohde.thomas@gmail.com>`
- declare explicit package metadata in `pyproject.toml`, including description, license, Python requirement, and project URLs for Homepage, Repository, and Issues
- use a `src/` layout with `src/cwmem`
- keep the package version in `src/cwmem/__init__.py` and wire `pyproject.toml` to read it dynamically
- use `hatchling` as the build backend, mirroring ArchGuard
- expose the CLI via `[project.scripts]` with `cwmem = "cwmem.__main__:main"`
- `uv` preferred for local workflows
- local packaging and verification commands must include `uv sync`, `uv build`, `uv run pytest`, `uv run ruff check src/ tests/`, and `uv run pyright src/`
- installable both with `pip install cwmem` and `uv tool install cwmem`

### 22.3 Cross-platform constraints

Must support:

- macOS
- Linux
- Windows 11

Avoid mandatory native dependencies beyond what is reasonable for Python + SQLite.

### 22.4 Release automation and PyPI publishing

- mirror ArchGuard's split between CI validation and PyPI publishing
- add `.github/workflows/ci.yml` that runs on pull requests and pushes to the default branch; if the repo mirrors ArchGuard exactly, use `master`
- CI must:
  - check out the repository
  - install `uv` with `astral-sh/setup-uv`
  - run `uv sync`
  - run `uv run ruff check src/ tests/`
  - run `uv run pyright src/`
  - run `uv run pytest --tb=short`
- add `.github/workflows/publish.yml` that builds and publishes the distribution
- the publish workflow must use a `build` job that runs `uv build` and uploads `dist/` as the artifact `python-package-distributions`
- the publish workflow must use a separate `publish` job that downloads the build artifact and publishes it with `pypa/gh-action-pypi-publish@release/v1`
- configure the publish job with `skip-existing: true` so reruns are safe for already-published versions
- publish through PyPI Trusted Publisher / GitHub OIDC; do not store long-lived PyPI API tokens in repository secrets
- required permissions: `id-token: write` at the workflow or publishing-job level
- use a GitHub environment named `pypi` with URL `https://pypi.org/p/cwmem`
- configure the PyPI Trusted Publisher binding for owner `ThomasRohde`, repository `cwmem`, workflow `publish.yml`, and environment `pypi`
- the pending publisher has already been prepared in PyPI with project name `cwmem`, owner `ThomasRohde`, repository `cwmem`, workflow `publish.yml`, and environment `pypi`; the GitHub workflow and environment must match these values exactly
- important caveat from PyPI: a pending publisher does not reserve the project name by itself; the first successful publish must happen promptly so the `cwmem` project is created and the publisher becomes an ordinary trusted publisher
- release discipline must include a version bump, changelog update, successful `uv build`, and a verified install of the published package from PyPI

---

## 23. Suggested repository layout

```text
repo/
  .github/
    workflows/
      ci.yml
      publish.yml
    PULL_REQUEST_TEMPLATE.md
  .cwmem/
    memory.sqlite
    memory.sqlite.lock
    logs/
  memory/
    entries/
    events/
    graph/
    taxonomy/
    manifests/
  models/
    model2vec/
  src/
    cwmem/
      __init__.py
      __main__.py
      cli/
        setup.py
        read.py
        write.py
        graph.py
        sync.py
        maintenance.py
      core/
        models.py
        store.py
        ids.py
        fingerprints.py
        fts.py
        embeddings.py
        hybrid_search.py
        graph.py
        events.py
        export.py
        importer.py
        planner.py
        validator.py
        locking.py
      output/
        envelope.py
        json.py
        table.py
  pyproject.toml
  uv.lock
  tests/
  CHANGELOG.md
  CONTRIBUTING.md
  LICENSE
  PRD.md
  README.md
  AGENTS.md
```

---

## 24. Acceptance criteria

### 24.1 Core functional acceptance

1. A new repo can run `cwmem init` successfully.
2. A user can add, update, retrieve, and list memory entries.
3. A user can add tags and relations.
4. A user can append formal log events.
5. `cwmem search` returns hybrid results using BM25 + Model2Vec.
6. `cwmem graph show` returns a graph neighborhood.
7. `cwmem sync export` writes deterministic artifacts.
8. `cwmem sync import` reconstructs or updates SQLite from artifacts.
9. `cwmem validate` catches integrity violations.
10. `cwmem verify` can assert export/import consistency.

### 24.2 CLI contract acceptance

1. Every command returns the structured envelope.
2. Error codes are stable and documented.
3. Exit codes follow the documented contract.
4. `cwmem guide` returns machine-readable schemas and workflows.
5. Mutating commands support `--dry-run`.
6. stdout/stderr discipline is respected.
7. output precedence follows flags > env vars > `isatty()`.
8. locking and concurrency rules are enforced and documented.

### 24.3 Determinism acceptance

1. Exporting twice without logical changes yields byte-stable artifacts.
2. Import followed by export yields the same manifest fingerprint.
3. Rebuilding indexes does not change logical artifacts.

### 24.4 Packaging and release acceptance

1. `uv build` produces both a wheel and an sdist for `cwmem`.
2. `pyproject.toml` exposes complete publishable metadata for `cwmem`, including author, URLs, Python requirement, and the `cwmem` CLI entry point.
3. GitHub Actions CI runs lint, type checking, and tests on pull requests and pushes.
4. The publish workflow uses a build-artifact handoff between `build` and `publish` jobs.
5. PyPI publication works through Trusted Publisher / OIDC with the `pypi` environment and `id-token: write`, without a long-lived PyPI secret.
6. Re-running the publish workflow for an already-published version is safe because the publish step uses `skip-existing: true`.
7. The configured GitHub owner, repository, workflow filename, and environment exactly match the pending PyPI trusted publisher registration for `cwmem`.
8. The first release is published successfully so the pending publisher creates the PyPI project and converts into an ordinary trusted publisher.

---

## 25. Phase plan

Each phase should be small enough to fit one focused agentic coding session.

### Phase 1 — Core repository and envelope contract

Deliver:

- project scaffold
- `pyproject.toml` with package metadata and build backend
- `src/cwmem/__init__.py` as the package version source
- envelope models
- command skeleton
- `guide`
- `init`
- `status`
- exit code/error taxonomy

### Phase 2 — Core memory CRUD and event log

Deliver:

- entries/events schema
- `add`, `get`, `list`, `update`, `log`
- tags
- deterministic IDs
- markdown + JSONL export skeleton

### Phase 3 — SQLite FTS5 search

Deliver:

- FTS tables
- search indexing
- lexical search command
- filters
- stats/validate basics

### Phase 4 — Model2Vec embeddings and hybrid search

Deliver:

- local model handling
- embedding storage
- hybrid merge via RRF
- search explanation fields

### Phase 5 — Knowledge graph

Deliver:

- entity/edge schema
- `entity-add`, `link`, `related`, `graph show`
- graph export files
- graph-aware expansion in search

### Phase 6 — Sync workflows

Deliver:

- deterministic export/import
- export manifest
- `sync export --check`
- import round-trip tests

### Phase 7 — Safety, workflow, and concurrency hardening

Deliver:

- dry-run everywhere
- locking
- idempotency keys
- plan/validate/apply/verify for sync and batch workflows
- verify assertions

### Phase 8 — Automation hooks

Deliver:

- GitHub Actions CI verification
- PyPI build-and-publish workflow
- Trusted Publisher / OIDC configuration for the `pypi` environment
- first successful PyPI publish to activate the pending trusted publisher
- PR template and release checklist
- “learn from PR” placeholder hooks
- auto-tagging/edge extraction extension points

---

## 26. Risks and mitigations

### Risk: export/import drift

Mitigation:

- manifest fingerprints
- round-trip tests
- explicit verify command

### Risk: semantic search adds too much packaging complexity

Mitigation:

- use Model2Vec because it is lightweight
- keep vector similarity in Python for v1
- vendor model or pin it clearly

### Risk: graph extraction becomes noisy

Mitigation:

- require provenance and confidence
- make inferred edges visibly distinct
- prefer explicit relations in v1

### Risk: multi-agent corruption through concurrent writes

Mitigation:

- sidecar lock
- documented concurrency rules
- idempotency keys
- fingerprint checking

### Risk: Git diffs become noisy

Mitigation:

- deterministic serialization
- stable sort order
- one-entry-per-file for narrative memory
- append-only policy for events

---

## 27. Testing strategy

### 27.1 Unit tests

- IDs and public IDs
- envelope serialization
- error mapping
- fingerprinting
- export determinism
- import validation
- FTS indexing
- embedding serialization
- graph relation invariants

### 27.2 Integration tests

- init -> add -> search -> export
- import -> rebuild -> verify
- graph link -> related -> graph show
- dry-run flows
- lock contention behavior

### 27.3 Golden tests

Use golden files for:

- exported markdown
- export manifest
- guide output
- JSON envelopes

### 27.4 Contract tests

Ensure every command returns the minimum required envelope keys.

---

## 28. Open decisions

1. Whether the model is fully vendored in Git by default or fetched and pinned with a managed cache plus optional vendor command.
2. Whether entries should export only as markdown or also as JSONL for machine efficiency.
3. Whether inferred graph edges ship in v1 or v2.
4. Whether event creation on entry mutation is automatic by default or opt-in.
5. Whether `sync export` should be implicit after every write in agent mode or explicit only.

Recommended defaults:

- vendor the small model if repo size remains acceptable
- export entries as markdown plus manifest, not duplicate JSONL in v1 unless needed
- keep graph inference limited in v1
- emit lifecycle events automatically
- make sync explicit by default, with optional hooks/automation

---

## 29. Implementation recommendation

Build v1 as a single Python package with SQLite-backed domain logic and deterministic export/import workflows.

Do not overcomplicate the first version with:

- remote services
- vector database dependencies
- graph database dependencies
- auto-extraction everywhere

The winning design is:

- SQLite for runtime
- markdown/jsonl for collaboration
- FTS5 for BM25
- Model2Vec for semantic search
- RRF for hybrid retrieval
- explicit graph tables and exports
- agent-first CLI contract from day one

That gives you a practical institutional memory system that fits the Coworker repo instead of fighting it.

---

## 30. Source inputs

The design of this PRD was informed by:

- CLI-MANIFEST: `https://gist.githubusercontent.com/ThomasRohde/d4e99da015786674dbfd0233efb4f809/raw/42bf9031c89e79e3a5780e53ccf520234a74a4bd/CLI-MANIFEST.md`
- ArchGuard repo: `https://github.com/ThomasRohde/archguard`
- ArchGuard release automation reference: `pyproject.toml`, `.github/workflows/ci.yml`, `.github/workflows/publish.yml`, and `.github/PULL_REQUEST_TEMPLATE.md`
- Model2Vec: `https://github.com/MinishLab/model2vec`
