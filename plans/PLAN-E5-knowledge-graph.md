# Add knowledge graph commands and graph-aware search

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

## Purpose / Big Picture

After this change, the CLI can create entities and relationships, show why records are linked, and optionally expand search results through a small, explainable graph. To see it working, run `uv run cwmem entity-add`, `uv run cwmem link`, `uv run cwmem related`, and `uv run cwmem graph show`; the outputs should show explicit and inferred edges with provenance and confidence.

## Progress

- [ ] Verify that hybrid search and embedding rebuilds already work.
- [ ] Add entity, edge, and mapping tables plus graph export helpers.
- [ ] Implement `entity-add`, `link`, `related`, and `graph show`.
- [ ] Add deterministic inferred edges for v1 and graph-aware search expansion.
- [ ] Add tests for graph creation, graph traversal, export ordering, and explanation payloads.

## Surprises & Discoveries

No discoveries yet - this section will be populated during implementation.

## Decision Log

- Decision: Ship inferred graph edges in v1, but limit them to deterministic rule-based inference from existing structured data.
  Rationale: The user asked for inferred edges in v1, but the PRD warns that noisy graph extraction would harm trust.
  Source: User clarification on 2026-03-14 and PRD Section 26.

- Decision: Every edge stores provenance and confidence, and the CLI must surface both.
  Rationale: Graph expansion is only safe when humans and agents can see why a link exists.
  Source: PRD Sections 9.4 and 24.1.

- Decision: Graph-aware search expansion remains opt-in through `--expand-graph`.
  Rationale: Lexical and semantic results should stay predictable by default, while graph expansion remains conservative and explainable.
  Source: PRD Sections 8.5 and 12.4.

## Outcomes & Retrospective

To be completed at major milestones and at plan completion.

## Context and Orientation

This phase assumes the repository already supports entries, events, lexical search, semantic search, and a working `cwmem build` path. If `uv run cwmem search` does not already return hybrid results, complete the previous phase first.

The graph introduces two new resource types: entities and edges. An entity is a named thing such as a system, capability, domain, standard, technology, team, person, artifact, or initiative. An edge is a typed relationship between two resources with provenance and confidence. The key implementation files are `src/cwmem/core/graph.py`, `src/cwmem/core/store.py`, `src/cwmem/core/models.py`, `src/cwmem/core/hybrid_search.py`, `src/cwmem/cli/graph.py`, `src/cwmem/cli/write.py`, and tests in `tests/test_graph_cli.py` and `tests/test_graph_inference.py`.

The graph export surface is `memory/graph/nodes.jsonl` and `memory/graph/edges.jsonl`. These files must be sorted deterministically so a later sync phase can prove round-trip stability.

## Plan of Work

Extend the schema in `src/cwmem/core/store.py` to include `entities`, `edges`, `entity_tags`, and `entry_entities` if they are not already present. Add entity FTS indexing so `cwmem search` can include entity names and aliases. Extend `src/cwmem/core/models.py` with `EntityRecord`, `EdgeRecord`, `RelatedQuery`, and `GraphNeighborhood` models.

Implement `memory.entity.add` in `src/cwmem/cli/write.py` so users can create entities with a public ID such as `ent-000001`, a type, name, description, aliases, tags, status, provenance, and fingerprint. Implement `memory.link` so users can create explicit edges between entries, events, entities, or tags using relation types such as `related_to`, `depends_on`, or `supports`. Implement `memory.related` and `memory.graph.show` in `src/cwmem/cli/graph.py` so callers can traverse one or more hops, filter by relation type, and include provenance when requested.

Add deterministic inference in `src/cwmem/core/graph.py`. Keep v1 small: infer a low-confidence `related_to` edge when two entries share the same explicit entity reference and no explicit edge already exists. Mark these inferred edges with provenance `inferred_rule`, confidence `0.35`, and `created_by` set to `build`. Do not add model-generated edges in this phase.

Extend `src/cwmem/core/hybrid_search.py` so `--expand-graph` adds one-hop graph neighbors after lexical and semantic candidates are gathered. Expanded hits must state that they were found through graph expansion and identify the source edge.

## Concrete Steps

1. Confirm the prerequisite search behavior.

   From the repository root, run:

    uv run cwmem search "capability model" --limit 5
    uv run cwmem build

   Expected: hybrid search and build both succeed before graph changes begin.

2. Add the graph schema and typed models.

   Update `src/cwmem/core/store.py` with the entity and edge tables plus entity tag and entry/entity mapping tables. Extend `src/cwmem/core/models.py` with graph record and query models.

3. Implement graph write commands.

   Add `entity-add` and `link` command handlers. `entity-add` should allocate public IDs using the same counter style as entries and events. `link` should reject duplicate explicit edges with a conflict error and must persist provenance, confidence, and creator metadata.

4. Implement graph read commands.

   Add `related` and `graph show` handlers that can return a resource's neighborhood, filtered by relation type, entity type, and depth. The result payload should include the edge path that explains each returned node.

5. Add deterministic inferred edges and graph-aware search expansion.

   In `src/cwmem/core/graph.py`, infer edges from shared entity references only. Rebuild inferred edges during `cwmem build`, and update `cwmem search --expand-graph` so it surfaces one-hop neighbors with explicit explanation fields.

6. Add tests and validate from the repository root.

    uv run cwmem entity-add --entity-type capability --name "Business Capability Model"
    uv run cwmem link mem-000001 ent-000001 --relation supports --provenance explicit_user
    uv run cwmem related mem-000001 --depth 1 --include-provenance
    uv run cwmem graph show mem-000001 --depth 2
    uv run cwmem search "governance" --expand-graph --limit 5
    uv run pytest --tb=short

   Expected: explicit links are returned immediately, inferred links appear only after a build or graph refresh, and expanded search hits identify the source edge that pulled them into the result set.

## Validation and Acceptance

Run `uv run cwmem entity-add`, `uv run cwmem link`, `uv run cwmem related`, and `uv run cwmem graph show` from the repository root.

Expected behavior: entities receive stable public IDs, explicit links return `ok: true`, and graph read commands return nodes plus edges with provenance and confidence. A query with `--include-provenance` must show whether each edge is `explicit_user`, `imported`, or `inferred_rule`.

Run:

    uv run cwmem build
    uv run cwmem search "governance" --expand-graph

Expected behavior: one-hop neighbors may enter the result set, and each expanded hit includes `graph_expansion` in `match_modes` plus the edge that caused the expansion.

Then run:

    uv run pytest --tb=short
    uv run ruff check src/ tests/
    uv run pyright src/

Expected behavior: graph tests pass, graph export ordering is deterministic, and type checking remains clean.

## Idempotence and Recovery

Explicit graph commands must reject duplicate edges instead of silently creating multiple identical rows. The inferred-edge rebuild path must be repeatable: clear previously inferred edges, recompute them from current canonical data, and leave explicit edges untouched.

If a graph build fails, rerun `cwmem build`; do not hand-edit `edges` rows. Treat inferred edges as derived data that can always be regenerated from entries, entities, and explicit links.

## Artifacts and Notes

A graph-aware search hit should include an explanation similar to:

    {
      "resource_id": "mem-000011",
      "match_modes": ["semantic", "graph_expansion"],
      "explanation": {
        "expanded_from": "mem-000001",
        "via_edge": {
          "relation_type": "supports",
          "provenance": "explicit_user",
          "confidence": 1.0
        }
      }
    }

## Interfaces and Dependencies

The primary interfaces are `add_entity(...) -> EntityRecord`, `add_edge(...) -> EdgeRecord`, `infer_edges(...) -> list[EdgeRecord]`, `get_related(...) -> list[GraphLink]`, and `graph_show(...) -> GraphNeighborhood`. Extend the typed models with `EntityRecord`, `EdgeRecord`, `GraphLink`, `GraphNeighborhood`, and graph-aware `SearchHit` explanation fields.

This phase still uses only SQLite, `numpy`, and the already-vendored embedding model. Keep graph inference deterministic and rule-based so it remains explainable and easy to test.
