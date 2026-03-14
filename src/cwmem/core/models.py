from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Target(BaseModel):
    resource: str
    identifier: str | None = None


class CommandWarning(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class CommandError(BaseModel):
    code: str
    message: str
    retryable: bool
    suggested_action: str
    details: dict[str, Any] = Field(default_factory=dict)


class Metrics(BaseModel):
    duration_ms: int = 0


class Envelope(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    schema_version: str = "1.0"
    request_id: str
    ok: bool
    command: str
    target: Target
    result: Any = None
    warnings: list[CommandWarning] = Field(default_factory=list)
    errors: list[CommandError] = Field(default_factory=list)
    metrics: Metrics = Field(default_factory=Metrics)


class GuideFlag(BaseModel):
    name: str
    required: bool
    kind: str
    description: str


class GuideWorkflow(BaseModel):
    name: str
    steps: list[str]
    description: str


class GuideDocument(BaseModel):
    schema_version: str
    compatibility_policy: dict[str, Any]
    output_mode_policy: dict[str, Any]
    command_catalog: list[dict[str, Any]]
    input_schemas: dict[str, Any]
    output_schemas: dict[str, Any]
    error_codes: list[dict[str, Any]]
    exit_codes: dict[str, int]
    workflows: list[GuideWorkflow]
    concurrency_policy: dict[str, Any]
    storage_layout: dict[str, Any]
    import_export_contract: dict[str, Any]
    identifier_syntax: dict[str, Any]
    examples: list[dict[str, str]]


class InitResult(BaseModel):
    root: str
    created: list[str]
    existing: list[str]
    seed_files: list[str]


class StatusResult(BaseModel):
    initialized: bool
    package_version: str
    paths: dict[str, str]
    existing_paths: list[str]
    missing_paths: list[str]
    empty_surfaces: list[str]
    database_exists: bool
    taxonomy_seed_files: list[str]


class EntryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internal_id: str
    public_id: str
    title: str
    body: str
    type: str
    status: str
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    related_ids: list[str] = Field(default_factory=list)
    entity_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str
    created_at: str
    updated_at: str


class EventResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    role: str = "subject"


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internal_id: str
    public_id: str
    event_type: str
    body: str
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    resources: list[EventResource] = Field(default_factory=list)
    related_ids: list[str] = Field(default_factory=list)
    entity_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str
    occurred_at: str
    created_at: str


class EntityRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internal_id: str
    public_id: str
    entity_type: str
    name: str
    description: str
    status: str
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str
    created_at: str
    updated_at: str


class EdgeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internal_id: str
    public_id: str
    source_id: str
    source_type: str
    target_id: str
    target_type: str
    relation_type: str
    provenance: str
    confidence: float
    is_inferred: bool = False
    created_by: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str
    created_at: str
    updated_at: str


class CreateEntryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    body: str
    type: str = "note"
    status: str = "active"
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    related_ids: list[str] = Field(default_factory=list)
    entity_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateEntryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_id: str
    title: str | None = None
    body: str | None = None
    type: str | None = None
    status: str | None = None
    author: str | None = None
    provenance: dict[str, Any] | None = None
    related_ids: list[str] | None = None
    entity_refs: list[str] | None = None
    metadata: dict[str, Any] | None = None
    expected_fingerprint: str | None = None


class TagMutationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    tags: list[str] = Field(min_length=1)


class CreateEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    body: str
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    resources: list[EventResource] = Field(default_factory=list)
    related_ids: list[str] = Field(default_factory=list)
    entity_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: str | None = None


class CreateEntityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str
    name: str
    description: str = ""
    status: str = "active"
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateEdgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    target_id: str
    relation_type: str
    provenance: str = "explicit_user"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LogQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource: str | None = None
    event_type: str | None = None
    tag: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class ListEntriesQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str | None = None
    type: str | None = None
    status: str | None = None
    author: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class MutationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applied: bool
    resource_kind: Literal["entry", "event"]


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str
    tag: str | None = None
    type: str | None = None
    author: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    lexical_only: bool = False
    semantic_only: bool = False
    expand_graph: bool = False
    limit: int = Field(default=20, ge=1, le=200)


class SearchHitExplanation(BaseModel):
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    rrf_score: float | None = None
    matched_fields: list[str] = Field(default_factory=list)
    expanded_from: str | None = None
    via_edge: dict[str, Any] | None = None


class SearchHit(BaseModel):
    resource_id: str
    resource_type: str
    score: float
    match_modes: list[str]
    explanation: SearchHitExplanation


class ModelManifest(BaseModel):
    model_name: str
    model_version: str
    vector_dim: int
    model_path: str
    normalize: bool = True
    license: str = "MIT"
    notes: str = ""


class EmbeddingRecord(BaseModel):
    resource_id: str
    resource_type: str
    content_fingerprint: str
    model_version: str
    vector_blob: bytes  # numpy float32 array serialized with tobytes()


class RelatedQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    relation_type: str | None = None
    depth: int = Field(default=1, ge=1, le=4)
    limit: int = Field(default=50, ge=1, le=500)
    include_provenance: bool = False


class GraphNode(BaseModel):
    resource_id: str
    resource_type: str
    label: str


class RelatedHit(BaseModel):
    resource_id: str
    resource_type: str
    depth: int
    resource: GraphNode
    path: list[EdgeRecord] = Field(default_factory=list)


class GraphNeighborhood(BaseModel):
    root: GraphNode
    depth: int
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[EdgeRecord] = Field(default_factory=list)


class StatsResult(BaseModel):
    entries: int
    events: int
    entries_fts: int
    events_fts: int
    entities: int
    entities_fts: int
    edges: int = 0
    embeddings: int = 0
    last_build_at: str | None = None
    embedding_model: str | None = None


class ValidationIssue(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    ok: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class LockInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pid: int
    hostname: str
    acquired_at: str
    command: str
    request_id: str


class IdempotencyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str
    command_id: str
    request_hash: str
    request_id: str
    resource_ids: list[str] = Field(default_factory=list)
    response: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class DryRunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counts: dict[str, int] = Field(default_factory=dict)
    impacted_resources: list[str] = Field(default_factory=list)


class PlanArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    workflow: str
    command_id: str
    created_at: str
    plan_path: str
    request_hash: str
    options: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, int] = Field(default_factory=dict)
    impacted_resources: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)
    stats: StatsResult | None = None


class ExportFileRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    fingerprint: str
    size_bytes: int


class ExportModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    vector_dim: int


class ExportManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_version: str
    source_db_fingerprint: str
    counts: dict[str, int]
    files: dict[str, str]
    model: ExportModelInfo
    generated_at: str


class ExportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_dir: str
    check: bool = False
    changed: bool
    files: list[ExportFileRecord] = Field(default_factory=list)
    manifest: ExportManifest
    drift: list[dict[str, Any]] = Field(default_factory=list)


class ImportChangeSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    create_ids: list[str] = Field(default_factory=list)
    update_ids: list[str] = Field(default_factory=list)
    remove_ids: list[str] = Field(default_factory=list)
    unchanged_ids: list[str] = Field(default_factory=list)


class ImportPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_dir: str
    source_db_fingerprint: str
    generated_at: str
    entries: ImportChangeSet
    events: ImportChangeSet
    entities: ImportChangeSet
    edges: ImportChangeSet
    summary: dict[str, int] = Field(default_factory=dict)


class ImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool
    applied: bool
    source_dir: str
    plan: ImportPlan
    rebuilt: dict[str, int] = Field(default_factory=dict)
