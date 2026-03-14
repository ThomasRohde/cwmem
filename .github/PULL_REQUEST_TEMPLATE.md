## Summary

- What changed?
- Why was it needed?

## Memory and sync impact

- [ ] Runtime SQLite behavior changed
- [ ] Exported `memory/` artifacts changed
- [ ] Search / graph / verify behavior changed
- [ ] No user-facing memory behavior changed

## Safety review

- [ ] I used `--dry-run` where appropriate
- [ ] I verified lock / idempotency / plan semantics where relevant
- [ ] I ran `uv run cwmem sync export --check` when export artifacts were affected
- [ ] I ran `uv run cwmem verify` when runtime or export behavior changed

## Local validation

- [ ] `uv run ruff check src tests`
- [ ] `uv run pyright src`
- [ ] `uv run pytest --tb=short`
- [ ] `uv build`
