# Add vendored Model2Vec embeddings and hybrid search

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, `cwmem search` can retrieve matches by meaning as well as by exact words, and hybrid results merge lexical and semantic candidates into one ranked list with transparent explanations. To see it working, run `uv run cwmem build` and then `uv run cwmem search "business capability baseline"`; the result should include semantic or hybrid matches even when the exact query words are absent.

## Progress

- [ ] Verify that lexical search and build/validate commands already work.
- [ ] Vendor the local Model2Vec model and add a manifest that records model metadata.
- [ ] Add embedding storage and embedding rebuild logic.
- [ ] Implement semantic-only and hybrid search with reciprocal-rank fusion.
- [ ] Add tests for semantic retrieval, explanation fields, and model metadata handling.

## Surprises & Discoveries

No discoveries yet - this section will be populated during implementation.

## Decision Log

- Decision: Vendor the small Model2Vec model in the repository by default.
  Rationale: The user explicitly chose an offline-first vendored model instead of a fetched cache.
  Source: User clarification on 2026-03-14.

- Decision: Store embeddings in SQLite and compute cosine similarity in Python with `numpy`.
  Rationale: This keeps packaging cross-platform and avoids introducing a native SQLite vector extension in v1.
  Source: PRD Sections 8.4 and 22.3.

- Decision: Merge lexical and semantic candidates with reciprocal-rank fusion and expose explanation fields that show which retrieval modes contributed to each hit.
  Rationale: Hybrid retrieval is the product goal, but it must remain explainable for humans and agents.
  Source: PRD Sections 8.1, 8.5, and 24.1.

## Outcomes & Retrospective

To be completed at major milestones and at plan completion.

## Context and Orientation

This phase assumes Phase 3 already provides a working lexical search path and a `cwmem build` command that can rebuild operational indexes. If `uv run cwmem search --lexical-only` does not already work, finish the lexical phase first.

The new repository surface is `models/model2vec/`. That directory should contain a checked-in vendored model under `models/model2vec/model/` and a manifest file at `models/model2vec/manifest.json` that records `model_name`, `model_version`, `vector_dim`, the relative model path, and any licensing note worth preserving. The core implementation files are `src/cwmem/core/embeddings.py`, `src/cwmem/core/hybrid_search.py`, `src/cwmem/core/store.py`, `src/cwmem/cli/read.py`, and `src/cwmem/cli/maintenance.py`.

The phrase "semantic retrieval" means embedding query text and stored resources into the same vector space and ranking them by cosine similarity. The phrase "RRF" means reciprocal-rank fusion, a deterministic way to merge two ranked candidate lists by adding `1 / (k + rank)` style scores.

## Plan of Work

Populate `models/model2vec/` with the chosen small model and a repository-local manifest. Extend `src/cwmem/core/store.py` so it creates the `embeddings` table and the metadata keys for model name, model version, vector dimension, and `last_build_at`.

Implement `src/cwmem/core/embeddings.py` with a thin adapter that loads the vendored model from `models/model2vec/manifest.json`, embeds entry and event text deterministically, and writes rows into `embeddings` keyed by resource ID. Keep the stored content fingerprint alongside each vector so build logic can skip unchanged resources.

Implement `src/cwmem/core/hybrid_search.py` so `memory.search` can execute lexical-only, semantic-only, or hybrid queries. Hybrid mode should gather lexical candidates, gather semantic candidates, merge them with RRF, and return explanations that expose `lexical_rank`, `semantic_rank`, and the final hybrid score. Extend `cwmem build` so it rebuilds missing or stale embeddings after FTS is refreshed.

Add tests in `tests/test_embeddings.py` and `tests/test_hybrid_search.py`. Use a fake embedder for most unit tests so ranking logic is deterministic, and reserve one integration test for loading the vendored model directory and confirming metadata is recorded in SQLite.

## Concrete Steps

1. Confirm lexical search is healthy.

   From the repository root, run:

    uv run cwmem search "capability model" --lexical-only
    uv run cwmem build

   Expected: both commands succeed before semantic behavior is added.

2. Vendor the model and record its metadata.

   Place the serialized model files under `models/model2vec/model/`. Add `models/model2vec/manifest.json` with `model_name`, `model_version`, `vector_dim`, and `model_path`. Update `cwmem init` if necessary so a fresh repo preserves this directory layout.

3. Implement embedding storage and rebuild logic.

   In `src/cwmem/core/embeddings.py`, add functions to load the model, build the embedding text for each resource, compute vectors, and upsert rows into the `embeddings` table only when the source fingerprint changed.

4. Implement hybrid search.

   In `src/cwmem/core/hybrid_search.py`, merge lexical and semantic candidates with reciprocal-rank fusion. Update `src/cwmem/cli/read.py` so `cwmem search` supports `--semantic-only`, `--lexical-only`, and the default hybrid mode. Return `match_modes` and explanation fields in every hit.

5. Add tests and build verification.

   Write tests for cosine-similarity ranking, RRF ordering, explanation payloads, missing-model failure messages, and the metadata keys written during `cwmem build`.

6. Validate from the repository root.

    uv run cwmem build
    uv run cwmem search "business capability baseline" --semantic-only --limit 3
    uv run cwmem search "BCM alignment" --limit 5
    uv run pytest --tb=short

   Expected: `build` records model metadata, semantic-only search returns conceptually related hits, and hybrid search returns a mixed ranked list with explicit explanations.

## Validation and Acceptance

Run:

    uv run cwmem build
    uv run cwmem search "business capability baseline" --semantic-only
    uv run cwmem search "BCM alignment"

Expected behavior: the build reports a non-empty embedding count and stores model metadata in SQLite; semantic-only search returns results even when exact query tokens are weak; hybrid search returns hits whose `match_modes` include `semantic` or both `lexical` and `semantic`.

Then run:

    uv run pytest --tb=short
    uv run ruff check src/ tests/
    uv run pyright src/

Expected behavior: hybrid search tests pass and the repository remains lint-clean and type-safe.

## Idempotence and Recovery

`cwmem build` must be repeatable. Re-running it should skip resources whose content fingerprint and model version have not changed, and it should overwrite stale embedding rows when either input changes. If the vendored model directory is missing or incomplete, fail with a clear I/O-style error that names `models/model2vec/manifest.json` or the missing model path.

If an embedding rebuild is interrupted, rerun `cwmem build`; do not delete the main database. The embedding table is a cache derived from canonical resource text and can always be regenerated.

## Artifacts and Notes

A successful hybrid search hit should resemble:

    {
      "resource_id": "mem-000007",
      "resource_type": "entry",
      "match_modes": ["lexical", "semantic"],
      "explanation": {
        "lexical_rank": 4,
        "semantic_rank": 1,
        "rrf_score": 0.0323
      }
    }

## Interfaces and Dependencies

The important interfaces are `load_vendored_model(manifest_path: Path) -> Embedder`, `embed_resources(...)`, `rebuild_embeddings(...)`, and `hybrid_search(query: SearchQuery) -> list[SearchHit]`. Extend the typed models with `EmbeddingRecord`, `ModelManifest`, and richer `SearchHit` explanation fields.

The runtime dependencies remain `model2vec`, `numpy`, and stdlib `sqlite3`. Keep the semantic layer behind a small adapter so future model changes only affect `cwmem.core.embeddings` and the checked-in manifest.
