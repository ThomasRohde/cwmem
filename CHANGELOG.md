# Changelog

## 1.4.0

### Added

- Claude Code skill for cwmem (`skills/cwmem/`) — enables any agent to use cwmem out of the box
- Skill reference documentation (`skills/cwmem/references/commands.md`)

## 1.3.0

### Changed

- JSON output is now pretty-printed (indented) when running interactively, compact when piped
- `--help` uses Rich-formatted panels and colors in terminals, plain text when piped

## 0.2.1

### Added

- top-level `cwmem --version` and `cwmem -V`
- a fuller README with installation, quick-start, repository layout, safety, and release guidance

## 0.2.0

### Added

- repo-native memory entry, event, graph, search, sync, and verification workflows
- deterministic export/import artifacts under `memory/`
- dry-run, idempotency, sidecar locking, and `plan` / `apply` / `verify` support
- GitHub Actions CI and publish workflow scaffolding
- no-op automation extension hooks for future auto-tagging, edge extraction, and PR learning
