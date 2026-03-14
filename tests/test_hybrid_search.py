from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from cwmem.core import hybrid_search
from cwmem.core.models import SearchHit, SearchHitExplanation, SearchQuery
from tests.phase2_helpers import extract_entry, init_repo, run_ok
from tests.phase3_helpers import extract_search_hits, find_search_hit


def test_search_semantic_ranks_vectors_by_cosine_similarity(monkeypatch) -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE embeddings (
            resource_id TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            content_fingerprint TEXT NOT NULL,
            model_version TEXT NOT NULL,
            vector_blob BLOB NOT NULL,
            PRIMARY KEY (resource_id, resource_type)
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO embeddings(
            resource_id, resource_type, content_fingerprint, model_version, vector_blob
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                "mem-000001",
                "entry",
                "fp-1",
                "model-a",
                np.array([1.0, 0.0], dtype=np.float32).tobytes(),
            ),
            (
                "mem-000002",
                "entry",
                "fp-2",
                "model-a",
                np.array([0.0, 1.0], dtype=np.float32).tobytes(),
            ),
        ],
    )
    monkeypatch.setattr(
        "cwmem.core.embeddings.embed_query",
        lambda root, text: np.array([1.0, 0.0], dtype=np.float32),
    )

    hits = hybrid_search.search_semantic(Path("C:\\repo"), conn, SearchQuery(q="semantic", limit=2))

    assert [hit.resource_id for hit in hits] == ["mem-000001", "mem-000002"]
    assert hits[0].score > hits[1].score
    assert hits[0].match_modes == ["semantic"]


def test_search_hybrid_merges_rankings_with_rrf(monkeypatch) -> None:
    lexical_hits = [
        SearchHit(
            resource_id="mem-000001",
            resource_type="entry",
            score=10.0,
            match_modes=["lexical"],
            explanation=SearchHitExplanation(lexical_rank=1, matched_fields=["title"]),
        ),
        SearchHit(
            resource_id="mem-000003",
            resource_type="entry",
            score=5.0,
            match_modes=["lexical"],
            explanation=SearchHitExplanation(lexical_rank=2, matched_fields=["body"]),
        ),
    ]
    semantic_hits = [
        SearchHit(
            resource_id="mem-000002",
            resource_type="entry",
            score=0.99,
            match_modes=["semantic"],
            explanation=SearchHitExplanation(semantic_rank=1),
        ),
        SearchHit(
            resource_id="mem-000001",
            resource_type="entry",
            score=0.95,
            match_modes=["semantic"],
            explanation=SearchHitExplanation(semantic_rank=2),
        ),
    ]
    monkeypatch.setattr(hybrid_search._fts, "search_lexical", lambda conn, query: lexical_hits)
    monkeypatch.setattr(hybrid_search, "search_semantic", lambda root, conn, query: semantic_hits)

    hits = hybrid_search.search_hybrid(
        Path("C:\\repo"),
        sqlite3.connect(":memory:"),
        SearchQuery(q="hybrid", limit=3),
    )

    assert [hit.resource_id for hit in hits] == ["mem-000001", "mem-000002", "mem-000003"]
    assert hits[0].match_modes == ["lexical", "semantic"]
    assert hits[0].explanation.lexical_rank == 1
    assert hits[0].explanation.semantic_rank == 2
    assert hits[0].explanation.rrf_score is not None
    assert hits[0].explanation.matched_fields == ["title"]


def test_hybrid_search_explanation_contains_rrf_score(run_cli, tmp_path: Path) -> None:
    """A hit that appears in both lexical and semantic results must carry an
    explanation with ``rrf_score``, ``lexical_rank``, and ``semantic_rank`` set.
    """
    init_repo(run_cli, tmp_path)

    entry = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Governance framework alignment",
            "--type",
            "decision",
            "--author",
            "alice",
            "Governance framework alignment ensures consistent policy enforcement.",
        )
    )
    run_ok(run_cli, tmp_path, "build")

    # Default search uses the hybrid path (neither --lexical-only nor --semantic-only)
    payload = run_ok(
        run_cli,
        tmp_path,
        "search",
        "governance framework",
        "--limit",
        "5",
    )
    hits = extract_search_hits(payload)
    hit = find_search_hit(hits, entry["public_id"])
    assert hit is not None, f"Expected entry not found in hybrid hits: {hits}"

    explanation = hit.get("explanation") or {}
    # Any dual-mode hit (lexical + semantic) must carry an rrf_score
    if "lexical" in hit["match_modes"] and "semantic" in hit["match_modes"]:
        assert explanation.get("rrf_score") is not None, explanation
        assert isinstance(explanation.get("lexical_rank"), int), explanation
        assert isinstance(explanation.get("semantic_rank"), int), explanation
