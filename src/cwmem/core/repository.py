from __future__ import annotations

from pathlib import Path

from cwmem import __version__
from cwmem.core.models import StatusResult
from cwmem.core.paths import EMPTY_SURFACES, REQUIRED_DIRECTORIES, TAXONOMY_SEEDS, relpath


def build_status_result(root: Path) -> StatusResult:
    existing_paths: list[str] = []
    missing_paths: list[str] = []

    for relative in REQUIRED_DIRECTORIES:
        path = root / relative
        (existing_paths if path.is_dir() else missing_paths).append(relpath(path, root))

    taxonomy_files: list[str] = []
    for relative in TAXONOMY_SEEDS:
        path = root / relative
        if path.is_file():
            taxonomy_files.append(relpath(path, root))
        else:
            missing_paths.append(relpath(path, root))

    database_file = root / ".cwmem" / "memory.sqlite"
    if database_file.is_file():
        existing_paths.append(relpath(database_file, root))
    else:
        missing_paths.append(relpath(database_file, root))

    model_manifest = root / "models" / "model2vec" / "manifest.json"
    if model_manifest.is_file():
        existing_paths.append(relpath(model_manifest, root))
    else:
        missing_paths.append(relpath(model_manifest, root))

    empty_surfaces = [
        relpath(root / relative, root)
        for relative in EMPTY_SURFACES
        if (root / relative).is_dir() and not any((root / relative).iterdir())
    ]

    initialized = not missing_paths
    return StatusResult(
        initialized=initialized,
        package_version=__version__,
        paths={
            "runtime_dir": relpath(root / ".cwmem", root),
            "log_dir": relpath(root / ".cwmem" / "logs", root),
            "plan_dir": relpath(root / ".cwmem" / "plans", root),
            "memory_dir": relpath(root / "memory", root),
            "taxonomy_dir": relpath(root / "memory" / "taxonomy", root),
            "model_dir": relpath(root / "models" / "model2vec", root),
            "model_manifest_path": relpath(model_manifest, root),
            "database_path": relpath(database_file, root),
            "lock_path": relpath(root / ".cwmem" / "memory.sqlite.lock", root),
        },
        existing_paths=sorted(set(existing_paths)),
        missing_paths=sorted(set(missing_paths)),
        empty_surfaces=empty_surfaces,
        database_exists=database_file.is_file(),
        taxonomy_seed_files=taxonomy_files,
    )
