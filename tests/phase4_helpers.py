"""Shared helpers for Phase 4 (embeddings / hybrid-search) tests."""

from __future__ import annotations

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_SRC = REPO_ROOT / "models"
MANIFEST_PATH = MODELS_SRC / "model2vec" / "manifest.json"
MODEL_DIR = MODELS_SRC / "model2vec" / "model"

_HF_HUB_CACHE = Path.home() / ".cache" / "huggingface" / "hub"


def hf_cache_snapshot(model_id: str) -> Path | None:
    """Return the local HF cache snapshot directory for *model_id*, or None.

    Resolves via the ``refs/main`` pointer so callers don't need to hard-code
    the commit hash.  Returns ``None`` when the cache is absent.
    """
    model_dir = _HF_HUB_CACHE / ("models--" + model_id.replace("/", "--"))
    refs_main = model_dir / "refs" / "main"
    if not refs_main.exists():
        return None
    commit = refs_main.read_text(encoding="utf-8").strip()
    snapshot = model_dir / "snapshots" / commit
    return snapshot if snapshot.is_dir() else None


def setup_vendored_model(tmp_path: Path) -> bool:
    """Copy the vendored models/ directory into *tmp_path* so that ``cwmem build``
    can find the manifest.

    Returns ``True`` if the model files were available and copied, ``False``
    otherwise (calling test should skip).
    """
    if not MANIFEST_PATH.exists() or not MODEL_DIR.exists():
        return False
    dest = tmp_path / "models"
    if dest.exists():
        return True  # already set up
    shutil.copytree(MODELS_SRC, dest)
    return True


def model_available() -> bool:
    """Return True when the vendored model is present in the project tree."""
    return MANIFEST_PATH.exists() and MODEL_DIR.exists()
