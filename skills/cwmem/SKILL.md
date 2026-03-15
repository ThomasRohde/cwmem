---
name: cwmem
description: >
  Record decisions, changes, events, and knowledge into cwmem — repo-native
  institutional memory for any git repo. Triggers on: meaningful changes
  (architecture decisions, process changes, meeting outcomes), user requests to
  "remember"/"record"/"log"/"track", mentions of "cwmem"/"institutional memory"/
  "decision log"/"knowledge base", or CLAUDE.md/AGENTS.md instructions.
  Proactively offer to record important decisions.
---

# cwmem Skill

Record and retrieve institutional memory for any git repo. Fast SQLite state + checked-in `memory/` artifacts.

## Resolve command

1. If `pyproject.toml` declares cwmem dependency: `uv run cwmem`
2. Else if `cwmem` on PATH: `cwmem`
3. Else: `uvx cwmem`

Store resolved prefix as `<cmd>` for the session.

## Initialization

Run `<cmd> status`. If not initialized, ask the user:
1. What kind of repository?
2. Default author?
3. Initial entities to track?

Then run `<cmd> init`, create entities with `<cmd> entity-add --name "<name>" --type "<type>" "<description>"`, then `<cmd> build`.

## Write operations

**Entries** (types: note, decision, bug, change, risk, todo, adr):

```bash
<cmd> add --title "Short title" --type decision --tag architecture \
  --entity "ent-000001" --relate "mem-000003" \
  "Rationale and alternatives considered."
```

`--entity`/`--relate` are optional; link to existing resources.

**Events** (types: deployment, incident, review, milestone, release):

```bash
<cmd> event-add --event-type deployment --tag release "Deployed v2.1.0"
```

**Entities** — durable graph nodes (services, APIs, teams, standards):

```bash
<cmd> entity-add --name "UserService" --type service "Handles auth and profiles"
```

**Links** (types: relates_to, implements, depends_on, supersedes, caused_by, owned_by):

```bash
<cmd> link mem-000001 ent-000002 --relation-type implements
```

## Read and sync

```bash
<cmd> search "authentication refactor"
<cmd> search "auth" --type decision --tag security
<cmd> list --type decision --limit 10
```

After writes, run `<cmd> sync export` to update checked-in artifacts.

## Proactive recording

After meaningful work, offer to record it: architecture/process decisions, bug root causes, refactoring rationale, meeting outcomes, dependency changes, standards.

Keep entries concise: clear title, rationale, enough context for 6-month recall.

## Reference and safety

Full commands: `references/commands.md`. Use `--dry-run` before unfamiliar mutations, `--idempotency-key` for retries. Never hand-edit `memory/`; parse `.ok` in JSON output.
