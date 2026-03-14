# Add CI, publishing, and automation extension hooks

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, the project is ready for routine contribution and release: pull requests run CI automatically, releases can publish to PyPI through GitHub OIDC, and the codebase exposes placeholder hooks for future automation such as auto-tagging and PR learning. To see it working, run the local quality gate, build a distribution, inspect the workflow files, and then push a branch so GitHub Actions executes the same checks.

## Progress

- [ ] Verify that the full feature set, tests, and package metadata already work locally.
- [ ] Add GitHub Actions CI and PyPI publish workflows.
- [ ] Add PR template, contribution guidance, changelog, and release checklist updates.
- [ ] Add placeholder automation hook interfaces without changing default runtime behavior.
- [ ] Validate local build/install behavior and confirm workflow configuration matches the Trusted Publisher settings.

## Surprises & Discoveries

No discoveries yet - this section will be populated during implementation.

## Decision Log

- Decision: The workflow filenames remain exactly `.github/workflows/ci.yml` and `.github/workflows/publish.yml`.
  Rationale: The PyPI Trusted Publisher binding already expects `publish.yml`, and the PRD requires these exact workflow names.
  Source: PRD Section 22.4.

- Decision: The publish workflow uses a separate `build` job that uploads `dist/` as `python-package-distributions`, and a separate `publish` job that downloads and publishes that artifact with `skip-existing: true`.
  Rationale: This is the required release pattern and makes reruns safe for already-published versions.
  Source: PRD Section 22.4.

- Decision: Placeholder automation hooks live in `src/cwmem/core/automation.py` and are opt-in no-ops by default.
  Rationale: The PRD asks for extension points, not active background automation that changes repository behavior unexpectedly.
  Source: PRD Phase 8 and Section 29.

- Decision: The CI workflow should target the actual repository default branch discovered at execution time; if the repository has not chosen yet, use `main` and record the branch name used when the workflow is committed.
  Rationale: The PRD allows either the real default branch or `master` when mirroring ArchGuard, so the plan must adapt to the live repository setting.
  Source: PRD Section 22.4.

## Outcomes & Retrospective

To be completed at major milestones and at plan completion.

## Context and Orientation

This phase assumes the package, test suite, sync workflows, safety features, and verification commands already exist. If `uv build`, `uv run pytest --tb=short`, `uv run ruff check src/ tests/`, and `uv run pyright src/` do not already succeed, stop and fix those issues before adding automation.

The GitHub-facing files live under `.github/`. The release-facing repository files are `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `AGENTS.md`, and `.github/PULL_REQUEST_TEMPLATE.md`. The new automation extension surface is `src/cwmem/core/automation.py`. The package must remain publishable as `cwmem`, and the GitHub environment name for publishing must be `pypi`.

## Plan of Work

Add `.github/workflows/ci.yml` so pull requests and pushes to the default branch run `uv sync`, `uv run ruff check src/ tests/`, `uv run pyright src/`, and `uv run pytest --tb=short`. Add `.github/workflows/publish.yml` so a release or manual dispatch builds the package in a `build` job with `uv build`, uploads `dist/` as `python-package-distributions`, and then publishes that artifact in a separate `publish` job using `pypa/gh-action-pypi-publish@release/v1` with `skip-existing: true` and `id-token: write`.

Update `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, and `AGENTS.md` so contributors know the local commands, release sequence, default sync policy, safety flags, and publish prerequisites. Add `.github/PULL_REQUEST_TEMPLATE.md` so changes to memory behavior, export determinism, and workflow configuration are reviewed explicitly.

Create `src/cwmem/core/automation.py` with small protocol-style interfaces or callables for `auto_tag`, `extract_edges`, and `learn_from_pr`, plus a registry that defaults to no-op implementations. These hooks must not run automatically in normal CLI commands yet; they only define extension points for a later phase or plugin.

Add tests in `tests/test_package_metadata.py` and `tests/test_automation_hooks.py` that assert the package metadata is complete enough to build and that the default automation hook registry is inert.

## Concrete Steps

1. Verify the local release baseline.

   From the repository root, run:

    uv build
    uv run pytest --tb=short
    uv run ruff check src/ tests/
    uv run pyright src/

   Expected: the project is already releasable locally before workflow automation is added.

2. Add GitHub Actions CI.

   Create `.github/workflows/ci.yml` with checkout, `astral-sh/setup-uv`, `uv sync`, `uv run ruff check src/ tests/`, `uv run pyright src/`, and `uv run pytest --tb=short`. Set the workflow triggers to pull requests and pushes to the repository's actual default branch.

3. Add the publish workflow.

   Create `.github/workflows/publish.yml` with a `build` job and a `publish` job. Ensure the publish job downloads the `python-package-distributions` artifact, runs with `id-token: write`, targets the `pypi` environment, and sets `skip-existing: true`.

4. Add contribution and release documentation.

   Update `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `AGENTS.md`, and `.github/PULL_REQUEST_TEMPLATE.md` so they document the CLI contract, local quality gates, sync/export review expectations, and the release checklist for version bumps and PyPI publication.

5. Add automation extension points.

   Create `src/cwmem/core/automation.py` with no-op default hooks and typed interfaces for future auto-tagging, edge extraction, and PR-learning integrations. Keep the hooks disabled by default and cover that behavior with unit tests.

6. Validate locally and prepare for GitHub execution.

    uv build
    python -m pip install --force-reinstall dist/*.whl
    uv run pytest --tb=short
    uv run ruff check src/ tests/
    uv run pyright src/

   Expected: the wheel and sdist build successfully, the local install works, and the same commands that CI will run already pass before the workflow files are committed.

## Validation and Acceptance

Run the local quality gate:

    uv build
    uv run pytest --tb=short
    uv run ruff check src/ tests/
    uv run pyright src/

Expected behavior: all local checks pass and `dist/` contains both a wheel and an sdist for `cwmem`.

Inspect `.github/workflows/ci.yml` and `.github/workflows/publish.yml`.

Expected behavior: the CI workflow runs the required `uv` commands; the publish workflow uses separate `build` and `publish` jobs, the artifact name `python-package-distributions`, `id-token: write`, the `pypi` environment, and `skip-existing: true`.

After pushing to GitHub, the acceptance criteria continue on the hosted side: pull requests should run CI automatically, and a release or manual publish run should produce or publish the distribution without requiring a long-lived PyPI token.

## Idempotence and Recovery

Re-running the CI workflow is naturally safe because it is read-only. Re-running the publish workflow for an already-published version must also be safe because the publish step uses `skip-existing: true`.

If a local release build fails, fix the package metadata or code and rerun `uv build`; do not edit `dist/` artifacts manually. If GitHub Actions configuration is wrong, update the YAML files and rerun the workflow rather than trying to patch state in the GitHub UI, except for the one-time `pypi` environment and Trusted Publisher binding that must match the documented values exactly.

## Artifacts and Notes

The local release gate for this phase is the command block:

    uv build
    uv run pytest --tb=short
    uv run ruff check src/ tests/
    uv run pyright src/

A successful publish configuration also includes the fixed values `owner: ThomasRohde`, `repository: cwmem`, `workflow: publish.yml`, and `environment: pypi` in the GitHub/PyPI setup.

## Interfaces and Dependencies

The key files are `.github/workflows/ci.yml`, `.github/workflows/publish.yml`, `.github/PULL_REQUEST_TEMPLATE.md`, `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `AGENTS.md`, and `src/cwmem/core/automation.py`. The automation module should expose small interfaces such as `AutoTagHook`, `EdgeExtractionHook`, and `PrLearningHook`, plus a registry that returns no-op implementations by default.

This phase depends on the existing Python package metadata, GitHub Actions, `astral-sh/setup-uv`, and `pypa/gh-action-pypi-publish@release/v1`. Keep the default runtime behavior unchanged; these additions should improve contribution and release workflows without mutating user memory automatically.
