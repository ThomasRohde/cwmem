from __future__ import annotations

from pathlib import Path

REQUIRED_DIRECTORIES: tuple[str, ...] = (
    ".cwmem",
    ".cwmem/logs",
    ".cwmem/plans",
    "memory/entries",
    "memory/events",
    "memory/graph",
    "memory/taxonomy",
    "memory/manifests",
    "models/model2vec",
)

EMPTY_SURFACES: tuple[str, ...] = (
    "memory/entries",
    "memory/events",
    "memory/graph",
    "memory/manifests",
    "models/model2vec",
)

TAXONOMY_SEEDS: dict[str, dict[str, object]] = {
    "memory/taxonomy/tags.json": {
        "schema_version": "1.0",
        "taxonomy": "tags",
        "items": [
            "architecture",
            "decision",
            "finding",
            "initiative",
            "meeting",
            "reference",
            "standard",
        ],
    },
    "memory/taxonomy/relation-types.json": {
        "schema_version": "1.0",
        "taxonomy": "relation-types",
        "items": [
            "contradicts",
            "depends_on",
            "derived_from",
            "influences",
            "mentions",
            "owned_by",
            "references",
            "related_to",
            "supersedes",
            "supports",
        ],
    },
    "memory/taxonomy/entity-types.json": {
        "schema_version": "1.0",
        "taxonomy": "entity-types",
        "items": [
            "capability",
            "domain",
            "initiative",
            "person",
            "repo_artifact",
            "standard",
            "system",
            "team",
            "technology",
        ],
    },
}


def relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix() or "."
    except ValueError:
        return path.resolve().as_posix()

