---
name: cwmem
description: >
  Record decisions, changes, events, and knowledge into cwmem — a repo-native
  institutional memory system. Use this skill in any git-managed repository:
  software projects, documentation repos, enterprise architecture governance,
  meeting records, process automation, or any work that benefits from
  institutional memory. Triggers when you make meaningful changes (architecture
  decisions, process changes, meeting outcomes, document revisions), when the
  user asks you to "remember", "record", "log", or "track" something, when
  CLAUDE.md or AGENTS.md instructs you to use cwmem, or when you need to search
  or recall past decisions and context. Also triggers on mentions of "cwmem",
  "institutional memory", "decision log", "changelog entry", or "knowledge base".
  Proactively offer to record important decisions even if the user doesn't
  explicitly ask — a brief "Want me to record this decision in cwmem?" goes a
  long way.
---

# cwmem Skill

Record and retrieve institutional memory for any git-managed repository —
software projects, documentation, enterprise architecture, governance processes,
and more. cwmem keeps fast operational state in SQLite while exporting
deterministic collaboration artifacts to a checked-in `memory/` directory.

## Step 0: Resolve the cwmem command

Before any cwmem operation, determine how to run it:

1. Check if the current directory has a `pyproject.toml` that declares cwmem as a
   dependency — if so, use `uv run cwmem`.
2. Otherwise, check if `cwmem` is on PATH — if so, use `cwmem` directly.
3. Otherwise, use `uvx cwmem` (installs and runs from PyPI on the fly).

Store the resolved command prefix (e.g. `uv run cwmem`, `cwmem`, or `uvx cwmem`)
and reuse it for all subsequent calls in this session.

## Step 1: Check initialization

Run `<cmd> status` to see if the repo has cwmem initialized. If you get an error
or the result shows the database doesn't exist, proceed to **Setup** below.
If already initialized, skip to **Step 2**.

### Setup (only if not initialized)

Ask the user these questions before initializing:

1. **What kind of repository is this?** (software project, documentation, EA governance, process repo, etc. — helps decide useful entry types and tags)
2. **Who should be listed as the default author?** (or leave blank for anonymous)
3. **Any initial entities to track?** (e.g. services, APIs, teams, capabilities, standards, stakeholders)

Then run:

```bash
<cmd> init
```

After init, if the user provided entities, create them:

```bash
<cmd> entity-add --name "<name>" --type "<type>" "<description>"
```

Finally, run `<cmd> build` to initialize the search index.

## Step 2: Choose the right operation

### Recording a decision or change

Use `add` with an appropriate `--type`:

```bash
<cmd> add --title "Short title" --type decision --tag architecture \
  "Body explaining the decision, rationale, and alternatives considered."
```

Common types: `note`, `decision`, `bug`, `change`, `risk`, `todo`, `adr`.

To link an entry to existing entities or other entries:

```bash
<cmd> add --title "Title" --type decision \
  --entity "ent-000001" --relate "mem-000003" \
  "Body text"
```

### Logging an event

Events are timestamped, append-only records of things that happened:

```bash
<cmd> event-add --event-type deployment --tag release \
  "Deployed v2.1.0 to production"
```

Common event types: `deployment`, `incident`, `review`, `milestone`, `release`.

### Adding an entity

Entities are long-lived things tracked in the knowledge graph — services, APIs,
teams, capabilities, standards, stakeholders, or any durable concept worth
tracking relationships for:

```bash
<cmd> entity-add --name "UserService" --type service \
  "Handles user authentication and profile management"

<cmd> entity-add --name "Data Governance Board" --type team \
  "Cross-functional board responsible for data quality standards"
```

### Linking resources

Create explicit relationships between any two resources:

```bash
<cmd> link mem-000001 ent-000002 --relation-type implements
```

Common relation types: `relates_to`, `implements`, `depends_on`, `supersedes`,
`caused_by`, `owned_by`.

### Searching memory

```bash
<cmd> search "authentication refactor"
<cmd> search "auth" --type decision --tag security
<cmd> list --type decision --limit 10
```

### After writes: sync artifacts

After one or more write operations, export the checked-in artifacts so they
appear in version control:

```bash
<cmd> sync export
```

## When to record proactively

After completing meaningful work, briefly offer to record it. Good candidates:

- **Architecture decisions** — why something was designed a certain way
- **Process decisions** — agreed workflows, governance changes, escalation paths
- **Meeting outcomes** — key decisions, action items, rationale from discussions
- **Bug root causes** — what went wrong and how it was fixed
- **Refactoring or restructuring rationale** — why something was reorganized
- **Dependency or tooling changes** — why something was added, removed, or upgraded
- **Standards and policies** — adopted conventions, compliance requirements

Keep entries concise. A good entry has a clear title, the rationale (why), and
enough context for someone to understand the decision 6 months later.

## Command reference

For the full list of commands, options, and output formats, read
`references/commands.md` in this skill directory.

## Safety conventions

- Use `--dry-run` before unfamiliar mutations to preview changes
- Use `--idempotency-key` when retrying writes in automated pipelines
- Never hand-edit files under `memory/` — always use `cwmem sync export`
- All commands output a JSON envelope on stdout; parse `.ok` to check success
