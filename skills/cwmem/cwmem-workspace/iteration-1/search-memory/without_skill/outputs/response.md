# Response: "What decisions have we made about the database layer? Search our memory."

## Approach

Without a dedicated cwmem skill, I would treat this as a file-search problem. Based on the CLAUDE.md instructions, I know:

1. The project keeps "checked-in JSONL/markdown artifacts" in a `memory/` directory.
2. The `.cwmem/memory.sqlite` database holds runtime state.

My approach would be:

1. **Explore the `memory/` directory** using `ls` to understand its structure (`entries/`, `events/`, `graph/`, `manifests/`, `taxonomy/`).
2. **Read `memory/entries/entries.jsonl`** since that is the JSONL artifact containing all memory entries.
3. **Grep for "database" or "SQLite"** across the entries to find relevant records.
4. **Read the matching markdown files** (e.g., `mem-000004.md`, `mem-000008.md`) for full rendered content.

### Tools I would use

- `Bash` (`ls`) to explore the `memory/` directory structure
- `Grep` to search for "database", "SQLite", "schema", "store" across `memory/entries/entries.jsonl` and the markdown files
- `Read` to read matching entries in full

### Estimated tool calls: 3-5

1. `ls memory/` and `ls memory/entries/`
2. `Grep` for "database|SQLite|schema" in `memory/entries/entries.jsonl`
3. `Read` the matching `.md` files (possibly 2-3 files)

## What I would say to the user

---

I searched the project's memory artifacts in `memory/entries/`. Here are the decisions and notes related to the database layer:

**1. Sidecar lock file for write serialization** (`memory/entries/mem-000004.md`, type: decision)

All mutating operations serialize through an exclusive sidecar lock file at `.cwmem/memory.sqlite.lock`, implemented via portalocker with fcntl/msvcrt fallbacks. The lock is non-blocking by default (`--wait-lock 0`); callers can specify a timeout in seconds. Lock metadata (PID, hostname, command, request_id, acquired_at) is written to a companion `.json` file for debugging stuck locks. Reads are lock-free and parallel-safe. This design was chosen over SQLite's built-in locking because sidecar files work across filesystems, are human-readable, and decouple lock semantics from SQLite pragma configuration.

**2. Fingerprint-based optimistic concurrency and rebuild optimization** (`memory/entries/mem-000005.md`, type: decision)

SHA256 fingerprints are computed from canonical JSON of content fields (excluding timestamps). They serve two purposes: (1) Optimistic concurrency control via `--expected-fingerprint` on update, which rejects stale writes with `ERR_CONFLICT_STALE_FINGERPRINT`; (2) Rebuild optimization for embeddings and FTS, where `content_fingerprint + model_version` comparisons skip re-encoding unchanged rows.

**3. Data model: entries, events, entities, edges** (`memory/entries/mem-000008.md`, type: note)

The cwmem data model has four core resource types stored in SQLite (schema v3): Entries (`mem-NNNNNN`), Events (`evt-NNNNNN`), Entities (`ent-NNNNNN`), and Edges (`edg-NNNNNN`). All resources use Crockford Base32 internal IDs and sequential public IDs. Self-links are rejected and duplicate edges are blocked.

**4. Deterministic sync export for version control** (`memory/entries/mem-000003.md`, type: decision)

cwmem splits state into runtime (`.cwmem/`) and tracked (`memory/`) directories. The sync export produces deterministic, git-friendly artifacts. The sync import workflow rebuilds the runtime database from tracked artifacts, enabling new clones to bootstrap from committed state.

**5. Embedding pipeline** (`memory/entries/mem-000012.md`, type: note)

The embedding pipeline stores 384-dim float32 vectors as raw bytes in the `embeddings` table. Fingerprint-based optimization makes incremental rebuilds fast -- only changed or new entries are re-encoded.

Additionally, the knowledge graph tracks **SQLite** as an entity (`ent-000002`): "Embedded relational database backing cwmem's runtime storage. Houses entries, events, entities, edges, FTS5 indexes, embeddings, and idempotency records. Schema version 3."

---

## Observations about working without a skill

Without a cwmem skill, I had to:

- **Manually explore the file system** to discover where memory is stored (the `memory/` directory and its subdirectories).
- **Read raw JSONL** and parse it visually to find relevant entries. The JSONL format is dense and not optimized for human scanning.
- **Guess at search terms** -- I would search for "database", "SQLite", "schema", "store", "lock", etc. and hope to cover the relevant entries. There is no semantic search available through file tools alone.
- **Spend 3-5 tool calls** just to discover and read the relevant content, compared to what could be a single `cwmem search` command.

Key limitations:
- No **semantic search** -- I can only do keyword matching via Grep, so I might miss entries that discuss the database layer using different terminology.
- No **graph traversal** -- I cannot follow edges from the "SQLite" entity to discover related decisions automatically.
- No **hybrid ranking** -- results are unranked; I have to manually judge relevance.
- The approach **does not scale** -- with 12 entries I can read them all, but with hundreds or thousands of entries, grep-based searching would be far less effective.
