from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from cwmem import __version__
from cwmem.core import embeddings as _emb
from cwmem.core.models import GuideDocument, GuideFlag, GuideWorkflow, InitResult, StatusResult
from cwmem.core.paths import EMPTY_SURFACES, REQUIRED_DIRECTORIES, TAXONOMY_SEEDS, relpath
from cwmem.core.store import ensure_schema
from cwmem.output.envelope import (
    AppError,
    conflict_error,
    not_implemented_error,
    run_cli_command,
)


def build_guide_document() -> GuideDocument:
    command_catalog = [
        {
            "name": "guide",
            "canonical_id": "system.guide",
            "implemented": True,
            "mutating": False,
            "summary": "Return machine-readable CLI documentation.",
            "aliases": [],
            "arguments": [],
            "output_schema": "GuideDocument",
        },
        {
            "name": "init",
            "canonical_id": "system.init",
            "implemented": True,
            "mutating": True,
            "summary": "Create runtime and tracked repository scaffolding.",
            "aliases": [],
            "arguments": [
                GuideFlag(
                    name="--cwd",
                    required=False,
                    kind="path",
                    description=(
                        "Repository root to initialize. Defaults to the current "
                        "working directory."
                    ),
                )
            ],
            "output_schema": "InitResult",
        },
        {
            "name": "status",
            "canonical_id": "system.status",
            "implemented": True,
            "mutating": False,
            "summary": "Report repository bootstrap status and known empty surfaces.",
            "aliases": [],
            "arguments": [
                GuideFlag(
                    name="--cwd",
                    required=False,
                    kind="path",
                    description=(
                        "Repository root to inspect. Defaults to the current "
                        "working directory."
                    ),
                )
            ],
            "output_schema": "StatusResult",
        },
        {
            "name": "get",
            "canonical_id": "memory.get",
            "implemented": True,
            "mutating": False,
            "summary": "Retrieve one memory item by identifier.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "list",
            "canonical_id": "memory.list",
            "implemented": True,
            "mutating": False,
            "summary": "List memory resources with filters.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "search",
            "canonical_id": "memory.search",
            "implemented": True,
            "mutating": False,
            "summary": "Run lexical and semantic retrieval over memory content.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "related",
            "canonical_id": "memory.related",
            "implemented": False,
            "mutating": False,
            "summary": "Find related memory items using graph and retrieval signals.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "log",
            "canonical_id": "memory.log",
            "implemented": True,
            "mutating": False,
            "summary": "Read the append-only event log.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "graph",
            "canonical_id": "memory.graph.show",
            "implemented": False,
            "mutating": False,
            "summary": "Inspect graph nodes and edges.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "stats",
            "canonical_id": "system.stats",
            "implemented": False,
            "mutating": False,
            "summary": "Report repository memory statistics.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "add",
            "canonical_id": "memory.add",
            "implemented": True,
            "mutating": True,
            "summary": "Create a memory entry.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "update",
            "canonical_id": "memory.update",
            "implemented": True,
            "mutating": True,
            "summary": "Patch a memory entry.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "deprecate",
            "canonical_id": "memory.deprecate",
            "implemented": False,
            "mutating": True,
            "summary": "Deprecate a memory item while preserving history.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "link",
            "canonical_id": "memory.link",
            "implemented": False,
            "mutating": True,
            "summary": "Create an explicit graph relationship.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "tag-add",
            "canonical_id": "memory.tag.add",
            "implemented": True,
            "mutating": True,
            "summary": "Attach one or more tags to a resource.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "tag-remove",
            "canonical_id": "memory.tag.remove",
            "implemented": True,
            "mutating": True,
            "summary": "Detach one or more tags from a resource.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "event-add",
            "canonical_id": "memory.event.add",
            "implemented": True,
            "mutating": True,
            "summary": "Append a formal event record.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "entity-add",
            "canonical_id": "memory.entity.add",
            "implemented": False,
            "mutating": True,
            "summary": "Create a graph entity record.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "sync export",
            "canonical_id": "memory.sync.export",
            "implemented": False,
            "mutating": True,
            "summary": "Export deterministic markdown and JSONL collaboration artifacts.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "sync import",
            "canonical_id": "memory.sync.import",
            "implemented": False,
            "mutating": True,
            "summary": "Rebuild runtime state from checked-in artifacts.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "build",
            "canonical_id": "system.build",
            "implemented": False,
            "mutating": True,
            "summary": "Build or rebuild derived runtime surfaces.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "plan",
            "canonical_id": "system.plan",
            "implemented": False,
            "mutating": True,
            "summary": "Generate a reviewable mutation plan.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "validate",
            "canonical_id": "system.validate",
            "implemented": False,
            "mutating": False,
            "summary": "Validate a plan or repository state before apply.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "apply",
            "canonical_id": "system.apply",
            "implemented": False,
            "mutating": True,
            "summary": "Apply a validated plan with drift protection.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
        {
            "name": "verify",
            "canonical_id": "system.verify",
            "implemented": False,
            "mutating": False,
            "summary": "Verify runtime and exported state are aligned.",
            "aliases": [],
            "arguments": [],
            "output_schema": "Envelope",
        },
    ]

    return GuideDocument(
        schema_version="1.0",
        compatibility_policy={
            "schema_version": "1.0",
            "stability": (
                "Canonical command IDs, envelope keys, and exit-code categories "
                "are stable within major version 0.x development."
            ),
        },
        output_mode_policy={
            "default": "json",
            "active": ["json"],
            "planned": ["table", "markdown"],
            "precedence": ["flags", "environment", "isatty"],
            "stdout_contract": "exactly one structured envelope",
            "stderr_contract": "diagnostics, progress, warnings, and logs only",
            "llm_mode": {
                "environment_variable": "LLM",
                "value": "true",
                "behavior": (
                    "No interactive prompts, JSON envelope on stdout, minimal "
                    "stderr noise."
                ),
            },
        },
        command_catalog=command_catalog,
        input_schemas={
            "system.guide": {"type": "object", "properties": {}, "additionalProperties": False},
            "system.init": {
                "type": "object",
                "properties": {"cwd": {"type": "string"}},
                "required": [],
                "additionalProperties": False,
            },
            "system.status": {
                "type": "object",
                "properties": {"cwd": {"type": "string"}},
                "required": [],
                "additionalProperties": False,
            },
        },
        output_schemas={
            "Envelope": {
                "required": [
                    "schema_version",
                    "request_id",
                    "ok",
                    "command",
                    "target",
                    "result",
                    "warnings",
                    "errors",
                    "metrics",
                ]
            },
            "GuideDocument": {
                "required": [
                    "schema_version",
                    "compatibility_policy",
                    "command_catalog",
                    "error_codes",
                    "exit_codes",
                    "workflows",
                    "concurrency_policy",
                    "storage_layout",
                    "import_export_contract",
                ]
            },
            "InitResult": {
                "required": ["root", "created", "existing", "seed_files"]
            },
            "StatusResult": {
                "required": [
                    "initialized",
                    "package_version",
                    "paths",
                    "existing_paths",
                    "missing_paths",
                    "empty_surfaces",
                    "database_exists",
                ]
            },
        },
        error_codes=[
            {
                "code": "ERR_VALIDATION_INPUT",
                "message": "Invalid user input or unsupported parameters.",
                "retryable": False,
            },
            {
                "code": "ERR_NOT_IMPLEMENTED",
                "message": "The command surface is planned but not implemented yet.",
                "retryable": False,
            },
            {
                "code": "ERR_AUTH_REQUIRED",
                "message": "A future command requires authentication or permissions.",
                "retryable": False,
            },
            {
                "code": "ERR_CONFLICT_STATE",
                "message": "Requested mutation conflicts with current repository state.",
                "retryable": False,
            },
            {
                "code": "ERR_CONFLICT_STALE_FINGERPRINT",
                "message": "Requested update used a stale fingerprint.",
                "retryable": False,
            },
            {
                "code": "ERR_LOCK_HELD",
                "message": "A write lock is already held by another process.",
                "retryable": True,
            },
            {
                "code": "ERR_IO_WRITE_FAILED",
                "message": "Filesystem or storage write failed.",
                "retryable": True,
            },
            {
                "code": "ERR_INTERNAL_UNHANDLED",
                "message": "An unexpected internal failure occurred.",
                "retryable": False,
            },
        ],
        exit_codes={
            "success": 0,
            "validation": 10,
            "auth": 20,
            "conflict": 40,
            "io": 50,
            "internal": 90,
        },
        workflows=[
            GuideWorkflow(
                name="bootstrap",
                steps=["guide", "init", "status"],
                description=(
                    "Discover the CLI, create local scaffolding, then inspect "
                    "the initialized repository state."
                ),
            ),
            GuideWorkflow(
                name="safe-mutation",
                steps=["plan", "validate", "apply", "verify"],
                description="High-risk workflows must stay reviewable and drift-aware.",
            ),
            GuideWorkflow(
                name="explicit-sync",
                steps=["sync export", "sync import"],
                description="Synchronization is explicit by default rather than automatic.",
            ),
        ],
        concurrency_policy={
            "reads_parallel": True,
            "writes_parallel": False,
            "lock_path": ".cwmem/memory.sqlite.lock",
            "write_policy": (
                "Planned policy: mutating commands will serialize through an "
                "exclusive sidecar lock."
            ),
            "enforcement_status": "planned for a later phase; not enforced by Phase 1 commands",
            "batch_guidance": (
                "Batch workflows may parallelize read phases but must serialize "
                "apply phases."
            ),
        },
        storage_layout={
            "runtime": [
                ".cwmem/",
                ".cwmem/logs/",
                ".cwmem/memory.sqlite",
                ".cwmem/memory.sqlite.lock",
            ],
            "tracked": [
                "memory/entries/",
                "memory/events/",
                "memory/graph/",
                "memory/taxonomy/",
                "memory/manifests/",
                "models/model2vec/",
            ],
        },
        import_export_contract={
            "entry_export_formats": ["markdown", "jsonl"],
            "event_export_format": "jsonl",
            "graph_export_formats": ["nodes.jsonl", "edges.jsonl"],
            "sync_mode": "explicit",
            "vendored_model_default": "enabled via repo-local model bundle",
            "graph_edges_v1": "explicit plus inferred edges",
            "lifecycle_events": "automatic",
        },
        identifier_syntax={
            "canonical_commands": "dotted identifiers such as system.guide and memory.sync.export",
            "request_id": "req_<UTC timestamp>_<8-char suffix>",
            "future_entry_ids": "stable internal IDs plus user-facing IDs",
        },
        examples=[
            {"command": "cwmem guide", "canonical_id": "system.guide"},
            {"command": "cwmem init", "canonical_id": "system.init"},
            {"command": "cwmem status", "canonical_id": "system.status"},
            {
                "command": 'cwmem add --title "Capability model" "Aligned the baseline."',
                "canonical_id": "memory.add",
            },
            {"command": "cwmem get mem-000001", "canonical_id": "memory.get"},
            {"command": "cwmem log --resource mem-000001", "canonical_id": "memory.log"},
        ],
    )


def _write_seed_file(path: Path, payload: dict[str, Any]) -> bool:
    import orjson

    if path.exists():
        if not path.is_file():
            raise conflict_error(
                "A taxonomy seed path exists but is not a file.",
                details={"path": path.as_posix()},
            )
        return False

    payload_bytes = orjson.dumps(
        payload,
        option=orjson.OPT_SORT_KEYS | orjson.OPT_APPEND_NEWLINE,
    )
    try:
        with path.open("xb") as handle:
            handle.write(payload_bytes)
        return True
    except FileExistsError:
        if path.is_file():
            return False
        raise conflict_error(
            "A taxonomy seed path exists but is not a file.",
            details={"path": path.as_posix()},
        ) from None


def _build_init_result(root: Path) -> InitResult:
    created: list[str] = []
    existing: list[str] = []
    db_preexisting = (root / ".cwmem" / "memory.sqlite").exists()
    model_manifest = root / "models" / "model2vec" / "manifest.json"
    model_manifest_preexisting = model_manifest.is_file()

    for relative in REQUIRED_DIRECTORIES:
        path = root / relative
        if path.exists() and not path.is_dir():
            raise conflict_error(
                "A required directory path exists but is not a directory.",
                details={"path": path.as_posix()},
            )
        already_exists = path.is_dir()
        path.mkdir(parents=True, exist_ok=True)
        (existing if already_exists else created).append(relpath(path, root))

    for relative, payload in TAXONOMY_SEEDS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        was_created = _write_seed_file(path, payload)
        (created if was_created else existing).append(relpath(path, root))

    _emb.ensure_repo_model(root)
    if model_manifest.is_file():
        (existing if model_manifest_preexisting else created).append(relpath(model_manifest, root))

    db_path = ensure_schema(root)
    db_relative = relpath(db_path, root)
    if db_relative in created or db_relative in existing:
        pass
    elif db_preexisting:
        existing.append(db_relative)
    elif db_path.exists():
        created.append(db_relative)

    seed_files = [relpath(root / relative, root) for relative in TAXONOMY_SEEDS]
    return InitResult(
        root=root.as_posix(),
        created=sorted(set(created)),
        existing=sorted(set(existing).difference(created)),
        seed_files=seed_files,
    )


def _build_status_result(root: Path) -> StatusResult:
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


def guide_command() -> None:
    raise SystemExit(run_cli_command("system.guide", "repository", lambda: build_guide_document()))


def init_command(cwd: Path | None = None) -> None:
    root = (cwd or Path.cwd()).resolve()
    raise SystemExit(run_cli_command("system.init", "repository", lambda: _build_init_result(root)))


def status_command(cwd: Path | None = None) -> None:
    root = (cwd or Path.cwd()).resolve()
    raise SystemExit(
        run_cli_command("system.status", "repository", lambda: _build_status_result(root))
    )


def register(app: typer.Typer) -> None:
    app.command("guide")(guide_command)
    app.command("init")(init_command)
    app.command("status")(status_command)


def placeholder_command(command_id: str, human_name: str) -> None:
    raise AppError.from_command_error(not_implemented_error(command_id, human_name))

