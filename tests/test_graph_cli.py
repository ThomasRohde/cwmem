from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from tests.phase2_helpers import extract_entry, init_repo, run_ok
from tests.phase3_helpers import (
    extract_search_hits,
    find_search_hit,
    memory_db_path,
    search_hit_resource_id,
)


def extract_entity(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    assert isinstance(result, dict), f"Expected object result, got: {type(result)!r}"
    entity = result.get("entity")
    assert isinstance(entity, dict), f"Expected `entity` object, got: {result!r}"
    return entity


def extract_edge(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    assert isinstance(result, dict), f"Expected object result, got: {type(result)!r}"
    edge = result.get("edge")
    assert isinstance(edge, dict), f"Expected `edge` object, got: {result!r}"
    return edge


def extract_related_hits(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload["result"]
    assert isinstance(result, dict), f"Expected object result, got: {type(result)!r}"
    hits = result.get("hits")
    assert isinstance(hits, list), f"Expected `hits` list, got: {result!r}"
    assert all(isinstance(hit, dict) for hit in hits), hits
    return hits


def extract_graph(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload["result"]
    assert isinstance(result, dict), f"Expected object result, got: {type(result)!r}"
    graph = result.get("graph")
    assert isinstance(graph, dict), f"Expected `graph` object, got: {result!r}"
    return graph


def test_entity_add_indexes_entities_for_lexical_search(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    entity = extract_entity(
        run_ok(
            run_cli,
            tmp_path,
            "entity-add",
            "--entity-type",
            "capability",
            "--name",
            "Business Capability Model",
            "--alias",
            "BCM",
            "--tag",
            "strategy",
            "Shared business capability vocabulary for retrieval tests.",
        )
    )

    search_payload = run_ok(
        run_cli,
        tmp_path,
        "search",
        "business capability model",
        "--lexical-only",
        "--limit",
        "10",
    )
    hit = find_search_hit(extract_search_hits(search_payload), entity["public_id"])
    assert hit is not None, search_payload
    assert hit["resource_type"] == "entity"
    assert "lexical" in hit["match_modes"]
    explanation = hit["explanation"]
    assert isinstance(explanation, dict), hit
    assert "name" in explanation["matched_fields"] or "aliases" in explanation["matched_fields"]


def test_entity_add_supports_legacy_entities_kind_schema(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    with sqlite3.connect(memory_db_path(tmp_path)) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute('DROP TABLE "entities"')
        conn.execute(
            """
            CREATE TABLE entities (
                internal_id TEXT PRIMARY KEY,
                public_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                aliases_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

    entity = extract_entity(
        run_ok(
            run_cli,
            tmp_path,
            "entity-add",
            "--entity-type",
            "capability",
            "--name",
            "Legacy schema entity",
        )
    )
    assert entity["public_id"].startswith("ent-")

    with sqlite3.connect(memory_db_path(tmp_path)) as conn:
        row = conn.execute(
            "SELECT kind, entity_type FROM entities WHERE public_id = ?",
            (entity["public_id"],),
        ).fetchone()
    assert row == ("capability", "capability")


def test_graph_and_related_show_explicit_links(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    entry = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Capability anchor",
            "--type",
            "decision",
            "Anchor entry for explicit graph traversal.",
        )
    )
    entity = extract_entity(
        run_ok(
            run_cli,
            tmp_path,
            "entity-add",
            "--entity-type",
            "capability",
            "--name",
            "Payments capability",
        )
    )
    edge = extract_edge(
        run_ok(
            run_cli,
            tmp_path,
            "link",
            entry["public_id"],
            entity["public_id"],
            "--relation",
            "references",
            "--provenance",
            "explicit_user",
        )
    )

    related_payload = run_ok(run_cli, tmp_path, "related", entry["public_id"], "--depth", "1")
    related_hit = find_search_hit(extract_related_hits(related_payload), entity["public_id"])
    assert related_hit is not None, related_payload
    assert related_hit["depth"] == 1
    assert related_hit["resource"]["label"] == entity["name"]
    path = related_hit["path"]
    assert isinstance(path, list) and path, related_hit
    assert path[0]["public_id"] == edge["public_id"]
    assert path[0]["relation_type"] == "references"
    assert path[0]["provenance"] == "explicit_user"

    graph_payload = run_ok(run_cli, tmp_path, "graph", entry["public_id"], "--depth", "1")
    graph = extract_graph(graph_payload)
    assert graph["root"]["resource_id"] == entry["public_id"]
    assert entity["public_id"] in {node["resource_id"] for node in graph["nodes"]}
    assert edge["public_id"] in {graph_edge["public_id"] for graph_edge in graph["edges"]}


def test_build_infers_related_edges_from_shared_entity_refs(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    entity = extract_entity(
        run_ok(
            run_cli,
            tmp_path,
            "entity-add",
            "--entity-type",
            "system",
            "--name",
            "Billing platform",
        )
    )
    first_entry = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Billing decision alpha",
            "--type",
            "decision",
            "--entity-ref",
            entity["public_id"],
            "Shared entity reference creates the graph inference seed alpha.",
        )
    )
    second_entry = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Billing decision beta",
            "--type",
            "decision",
            "--entity-ref",
            entity["public_id"],
            "Shared entity reference creates the graph inference seed beta.",
        )
    )

    before_build_payload = run_ok(
        run_cli,
        tmp_path,
        "related",
        first_entry["public_id"],
        "--depth",
        "1",
    )
    before_build_ids = {
        search_hit_resource_id(hit) for hit in extract_related_hits(before_build_payload)
    }
    assert second_entry["public_id"] not in before_build_ids

    run_ok(run_cli, tmp_path, "build")

    after_build_payload = run_ok(
        run_cli,
        tmp_path,
        "related",
        first_entry["public_id"],
        "--depth",
        "1",
    )
    inferred_hit = find_search_hit(
        extract_related_hits(after_build_payload),
        second_entry["public_id"],
    )
    assert inferred_hit is not None, after_build_payload
    inferred_edge = inferred_hit["path"][0]
    assert inferred_edge["relation_type"] == "related_to"
    assert inferred_edge["provenance"] == "inferred_rule"
    assert inferred_edge["is_inferred"] is True
    assert inferred_edge["metadata"]["shared_entity_refs"] == [entity["public_id"]]


def test_search_expand_graph_adds_neighbor_hit_with_explanation(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)

    anchor = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Governance anchor",
            "--type",
            "decision",
            "Rare governance anchor token for graph expansion.",
        )
    )
    neighbor = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Neighbor memory",
            "--type",
            "note",
            "This entry is only reachable through the explicit graph edge.",
        )
    )
    run_ok(
        run_cli,
        tmp_path,
        "link",
        anchor["public_id"],
        neighbor["public_id"],
        "--relation",
        "supports",
    )

    search_payload = run_ok(
        run_cli,
        tmp_path,
        "search",
        "rare governance anchor token",
        "--lexical-only",
        "--expand-graph",
        "--limit",
        "5",
    )
    hits = extract_search_hits(search_payload)
    assert find_search_hit(hits, anchor["public_id"]) is not None, hits
    neighbor_hit = find_search_hit(hits, neighbor["public_id"])
    assert neighbor_hit is not None, hits
    assert "graph_expansion" in neighbor_hit["match_modes"]
    explanation = neighbor_hit["explanation"]
    assert explanation["expanded_from"] == anchor["public_id"]
    assert explanation["via_edge"]["relation_type"] == "supports"
