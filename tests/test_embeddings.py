from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from model2vec import StaticModel

from tests.phase2_helpers import extract_entry, init_repo, run_any, run_ok
from tests.phase3_helpers import select_count, stats_count
from tests.phase4_helpers import hf_cache_snapshot


def test_build_populates_embeddings_and_records_model_metadata(run_cli, tmp_path: Path) -> None:
    init_repo(run_cli, tmp_path)

    extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Embedding baseline",
            "--type",
            "decision",
            "--author",
            "alice",
            "Embedding baseline content for semantic indexing.",
        )
    )

    build_payload = run_ok(run_cli, tmp_path, "build")
    assert build_payload["command"] == "system.build"
    result = build_payload["result"]
    assert isinstance(result, dict), result
    assert result["embeddings_written"] > 0

    stats_payload = run_ok(run_cli, tmp_path, "stats")
    stats_result = stats_payload["result"]
    assert isinstance(stats_result, dict), stats_result
    assert stats_count(stats_result, "embeddings", "embeddings_count") == (
        select_count(tmp_path, "entries") + select_count(tmp_path, "events")
    )
    assert stats_result.get("embedding_model") == "minishlab/potion-base-8M"


def test_validate_reports_stale_embeddings_after_entry_update_without_rebuild(
    run_cli, tmp_path: Path
) -> None:
    init_repo(run_cli, tmp_path)

    entry = extract_entry(
        run_ok(
            run_cli,
            tmp_path,
            "add",
            "--title",
            "Embedding drift target",
            "--type",
            "decision",
            "--author",
            "alice",
            "Original semantic payload before rebuild drift.",
        )
    )
    run_ok(run_cli, tmp_path, "build")

    run_ok(
        run_cli,
        tmp_path,
        "update",
        entry["public_id"],
        "--expected-fingerprint",
        entry["fingerprint"],
        "--body",
        "Updated semantic payload after the embedding rebuild baseline.",
    )

    completed, payload = run_any(run_cli, tmp_path, "validate")
    assert completed.returncode == 0, completed
    result = payload["result"]
    assert isinstance(result, dict), result
    assert result["ok"] is False

    serialized = json.dumps(payload, sort_keys=True).lower()
    assert "embedding" in serialized
    assert "drift" in serialized or "stale" in serialized or "resync" in serialized


def test_hf_cache_snapshot_loads_correct_vector_dim() -> None:
    """The HF-cached potion-base-8M snapshot must load and produce 256-dim vectors.

    This test is skipped when the HF cache is not present locally.  On the
    developer machine the cache is available offline, so it should always run.
    """
    snapshot = hf_cache_snapshot("minishlab/potion-base-8M")
    if snapshot is None:
        pytest.skip("HF cache for minishlab/potion-base-8M not found — run offline?")

    model = StaticModel.from_pretrained(snapshot)
    vectors = model.encode(["business capability baseline"])
    assert vectors.shape == (1, 256), vectors.shape
    assert vectors.dtype == np.float32


def test_build_idempotent_skips_unchanged_embeddings(run_cli, tmp_path: Path) -> None:
    """Running build twice on unchanged content must not re-embed any resource."""
    init_repo(run_cli, tmp_path)

    run_ok(
        run_cli,
        tmp_path,
        "add",
        "--title",
        "Idempotent embedding target",
        "--type",
        "decision",
        "--author",
        "alice",
        "Content whose embedding must not be recomputed on a second build.",
    )

    first = run_ok(run_cli, tmp_path, "build")
    assert first["result"]["embeddings_written"] > 0

    second = run_ok(run_cli, tmp_path, "build")
    assert second["result"]["embeddings_written"] == 0
