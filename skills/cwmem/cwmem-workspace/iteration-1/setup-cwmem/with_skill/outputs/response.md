# Simulated Interaction: "Set up cwmem in this project so we can start tracking architectural decisions."

**Context:** The user is working in a brand new git repo at `C:\Users\thoma\Projects\some-new-project`. The cwmem skill (`SKILL.md`) has been loaded.

---

## Phase 1: Resolve the cwmem command (Step 0)

The skill instructs me to determine how to run cwmem. I would run two checks in parallel:

### Commands I would run:

```bash
# Check 1: Does the project declare cwmem as a dependency?
cat C:/Users/thoma/Projects/some-new-project/pyproject.toml 2>/dev/null

# Check 2: Is cwmem on PATH?
which cwmem 2>/dev/null
```

### Expected outcome for a brand-new project:

- No `pyproject.toml` exists (or it doesn't list cwmem as a dependency).
- `cwmem` may or may not be on PATH.

### Resolution logic:

- If `pyproject.toml` lists cwmem: use `uv run cwmem`
- Else if `which cwmem` succeeds: use `cwmem`
- Else: use `uvx cwmem`

For this simulation, I'll assume `cwmem` is not a project dependency and not on PATH, so the resolved command is **`uvx cwmem`**.

---

## Phase 2: Check initialization (Step 1)

### Command I would run:

```bash
uvx cwmem status --cwd C:/Users/thoma/Projects/some-new-project
```

### Expected outcome:

This is a brand-new project, so cwmem is not initialized. The command would either error out or report that the database doesn't exist.

---

## Phase 3: Ask setup questions

Since cwmem is not initialized, the skill instructs me to ask the user three questions before proceeding. Here is what I would say to the user:

---

> I'll get cwmem set up for tracking architectural decisions in this project. Before I initialize it, I have a few questions:
>
> 1. **What kind of repository is this?** For example: software project, documentation repo, EA governance, process repo, etc. This helps me pick useful entry types and tags.
>
> 2. **Who should be listed as the default author?** (I can leave this blank if you prefer anonymous entries.)
>
> 3. **Any initial entities you'd like to track?** These are long-lived things in your knowledge graph -- for example, services, APIs, teams, capabilities, standards, or stakeholders. You can always add more later.

---

## Phase 4: Process user answers and initialize

Assuming the user responds with something like:

> 1. It's a software project -- a microservices platform.
> 2. Author: "Thomas Rohde"
> 3. Initial entities: "UserService" (service), "OrderService" (service), "API Gateway" (service), "Platform Team" (team)

### Commands I would run:

```bash
# Initialize cwmem
uvx cwmem init --cwd C:/Users/thoma/Projects/some-new-project
```

Then, create the entities the user requested:

```bash
# Create entities (run sequentially since they are writes)
uvx cwmem entity-add --name "UserService" --type service --cwd C:/Users/thoma/Projects/some-new-project "Handles user authentication and profile management"

uvx cwmem entity-add --name "OrderService" --type service --cwd C:/Users/thoma/Projects/some-new-project "Manages order lifecycle and processing"

uvx cwmem entity-add --name "API Gateway" --type service --cwd C:/Users/thoma/Projects/some-new-project "Edge service routing external requests to internal microservices"

uvx cwmem entity-add --name "Platform Team" --type team --cwd C:/Users/thoma/Projects/some-new-project "Team responsible for platform infrastructure and shared services"
```

Then build the search index:

```bash
uvx cwmem build --cwd C:/Users/thoma/Projects/some-new-project
```

Finally, export artifacts to the checked-in `memory/` directory:

```bash
uvx cwmem sync export --cwd C:/Users/thoma/Projects/some-new-project
```

---

## Phase 5: Confirm to the user

After all commands succeed, I would say:

---

> cwmem is set up and ready to go. Here's what was done:
>
> - Initialized the cwmem database at `.cwmem/` and the `memory/` artifact directory.
> - Created 4 entities in the knowledge graph:
>   - **UserService** (service)
>   - **OrderService** (service)
>   - **API Gateway** (service)
>   - **Platform Team** (team)
> - Built the search index (FTS + semantic embeddings).
> - Exported artifacts to `memory/` for version control.
>
> You can now start recording architectural decisions. For example:
>
> ```bash
> uvx cwmem add --title "Adopt event-driven architecture" --type decision --tag architecture \
>   "We decided to use an event-driven architecture with Kafka as the message broker to decouple services and improve resilience."
> ```
>
> After recording decisions, run `uvx cwmem sync export` to update the checked-in artifacts, then commit the `memory/` directory.
>
> Want me to record any architectural decisions you already have in mind?

---

## Summary of full interaction flow

| Step | Action | Skill Reference |
|------|--------|-----------------|
| 1 | Check `pyproject.toml` and `which cwmem` to resolve command prefix | Step 0 |
| 2 | Run `uvx cwmem status` to check if already initialized | Step 1 |
| 3 | Ask user 3 setup questions (repo type, author, initial entities) | Step 1 - Setup |
| 4 | Run `uvx cwmem init` | Step 1 - Setup |
| 5 | Run `uvx cwmem entity-add` for each entity the user specified | Step 1 - Setup |
| 6 | Run `uvx cwmem build` to initialize the search index | Step 1 - Setup |
| 7 | Run `uvx cwmem sync export` to generate checked-in artifacts | Step 2 - After writes |
| 8 | Confirm setup complete, show example usage, offer to record decisions | Proactive offer |

## Key observations about skill adherence

- The skill explicitly says to **ask the user three questions** before initializing. This is a blocking interaction -- I do not run `cwmem init` until I have the answers.
- The skill says to run `cwmem build` after creating entities, which initializes the FTS and semantic search indexes.
- The skill says to run `cwmem sync export` after write operations so artifacts appear in version control.
- The skill encourages **proactively offering** to record decisions, which I do at the end.
- The `--cwd` flag is used throughout since the working directory may not be the project root.
