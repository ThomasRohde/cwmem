# Research Program: Minimize cwmem SKILL.md Token Count

## Objective
Reduce the token count of `skills/cwmem/SKILL.md` as much as possible while preserving all functional guidance an agent needs to use cwmem correctly.

## Artifact
`skills/cwmem/SKILL.md` — a Claude Code skill file with YAML frontmatter (name + description) and markdown body. An agent reads this file and follows its instructions to operate the cwmem CLI.

## Evaluation
`python evaluate_skill.py` — counts approximate tokens (word + punctuation split). Exits non-zero if any required functional marker is missing. Lower is better.

The eval checks for ~20 required markers covering:
- Command resolution (uv run cwmem, uvx cwmem, PATH, pyproject.toml)
- Initialization check (status, init, setup questions with ?)
- Write operations (add --title, --type, event-add, entity-add, link)
- Read operations (search, list)
- Sync (sync export)
- Proactive recording guidance
- Safety (--dry-run)
- Reference to commands.md
- YAML frontmatter with name: cwmem and description:

## Constraints
- **Preserve the YAML frontmatter** — `name: cwmem` and `description:` are required. The description must contain enough triggering context for Claude to know when to use this skill.
- **Keep all functional behaviors** — an agent reading the optimized skill must produce the same quality output as the current version for these scenarios: recording a decision, setting up cwmem in a new repo, searching memory.
- **Don't remove the reference to `references/commands.md`** — progressive disclosure matters.
- **Keep the `<cmd>` placeholder pattern** — it's how the skill teaches command resolution.
- **Don't change references/commands.md** — only optimize SKILL.md.

## Strategy hints
- The current SKILL.md is verbose. Many instructions can be compressed without losing clarity.
- Combine related sections. Example: "Recording a decision or change" and "Logging an event" share similar patterns.
- Use terse imperative style instead of explanatory prose.
- Reduce example duplication — one good example per operation is enough.
- The description in frontmatter is important for triggering but could potentially be tightened.
- Headers and markdown structure cost tokens — flatten where possible.
- "Common types:" lists can be compressed to comma-separated inline.
- Look for repeated phrases and words that can be eliminated.
- The proactive recording section lists 7 bullet points — could be fewer.
