from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, ConfigDict
from caereflex.version import __version__
from .provenance import utc_now_iso


class InspectionStatus(str, Enum):
    success = "success"
    partial_success = "partial_success"
    failed = "failed"


class CaseType(str, Enum):
    unknown = "unknown"
    gmsh = "gmsh"
    openfoam = "openfoam"
    vtk = "vtk"
    mixed = "mixed"


class SourceKind(str, Enum):
    extracted = "extracted"
    inferred = "inferred"
    generated = "generated"
    user_supplied = "user_supplied"
    external_metadata = "external_metadata"


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"


class AssetType(str, Enum):
    geometry = "geometry"
    mesh = "mesh"
    case_folder = "case_folder"
    result_file = "result_file"
    dictionary = "dictionary"
    field = "field"
    literature = "literature"
    unknown = "unknown"


class EvidenceStatus(str, Enum):
    abstract_available = "abstract_available"
    metadata_only = "metadata_only"
    reference_only = "reference_only"
    unavailable = "unavailable"


class AdapterStatus(str, Enum):
    success = "success"
    partial_success = "partial_success"
    failed = "failed"
    dependency_missing = "dependency_missing"
    unsupported = "unsupported"


class FieldAssociation(str, Enum):
    point = "point"
    cell = "cell"
    field = "field"
    boundary = "boundary"
    volume = "volume"
    unknown = "unknown"


class FieldType(str, Enum):
    scalar = "scalar"
    vector = "vector"
    tensor = "tensor"
    unknown = "unknown"


class HashStatus(str, Enum):
    complete = "complete"
    skipped_large = "skipped_large"
    failed = "failed"
    not_applicable = "not_applicable"


class TraceInfo(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    source_kind: SourceKind = SourceKind.generated
    source_files: list[str] = Field(default_factory=list)
    adapter: str | None = None
    confidence: float = 1.0
    notes: list[str] = Field(default_factory=list)


class InspectionInfo(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    status: InspectionStatus = InspectionStatus.partial_success
    started_at: str = Field(default_factory=utc_now_iso)
    completed_at: str | None = None
    messages: list[str] = Field(default_factory=list)


class WorkspaceInfo(BaseModel):
    root_display: str = "."
    scan_depth: int = 0
    file_count_considered: int = 0
    limits: dict[str, Any] = Field(default_factory=dict)


class SourceFileRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    file_id: str
    relative_path: str
    suffix: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    hash_status: HashStatus = HashStatus.not_applicable
    metadata_subset: dict[str, Any] = Field(default_factory=dict)
    trace: TraceInfo = Field(default_factory=TraceInfo)


class EngineeringAsset(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    asset_id: str
    asset_type: AssetType = AssetType.unknown
    name: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    properties: dict[str, Any] = Field(default_factory=dict)
    trace: TraceInfo = Field(default_factory=TraceInfo)


class SolverRecord(BaseModel):
    name: str | None = None
    application: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    trace: TraceInfo = Field(default_factory=TraceInfo)


class BoundaryConditionRecord(BaseModel):
    patch: str
    field: str | None = None
    type: str | None = None
    value: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    trace: TraceInfo = Field(default_factory=TraceInfo)


class MaterialPropertyRecord(BaseModel):
    name: str
    value: str | float | int | None = None
    units: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    trace: TraceInfo = Field(default_factory=TraceInfo)


class NumericalSettingsRecord(BaseModel):
    category: str
    name: str
    value: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    trace: TraceInfo = Field(default_factory=TraceInfo)


class ResultFieldRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    name: str
    association: FieldAssociation = FieldAssociation.unknown
    field_type: FieldType = FieldType.unknown
    components: int | None = None
    statistics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    trace: TraceInfo = Field(default_factory=TraceInfo)


class LiteratureEvidenceRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    doi: str | None = None
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    container_title: str | None = None
    url: str | None = None
    abstract: str | None = None
    evidence_status: EvidenceStatus = EvidenceStatus.metadata_only
    relevance_score: float | None = None
    query: str | None = None
    metadata_subset: dict[str, Any] = Field(default_factory=dict)
    trace: TraceInfo = Field(default_factory=lambda: TraceInfo(source_kind=SourceKind.external_metadata, adapter="crossref"))


class LiteratureContext(BaseModel):
    queries: list[str] = Field(default_factory=list)
    records_used: list[str] = Field(default_factory=list)
    summary: str = ""
    limitations: list[str] = Field(default_factory=list)
    do_not_claim: list[str] = Field(default_factory=lambda: [
        "Do not claim that metadata-only records were read as full papers.",
        "Do not claim that CrossRef evidence validates the simulation.",
    ])


class InspectionFlag(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    severity: Severity = Severity.info
    category: str
    message: str
    trace: TraceInfo = Field(default_factory=TraceInfo)


class ProvenanceRecord(BaseModel):
    event: str
    timestamp: str = Field(default_factory=utc_now_iso)
    actor: str = "caereflex"
    details: dict[str, Any] = Field(default_factory=dict)


class AgentSummary(BaseModel):
    summary: str = ""
    safe_use_policy: list[str] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)
    do_not_claim: list[str] = Field(default_factory=list)


class ExportRecord(BaseModel):
    export_type: str
    relative_path: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class ReflexCase(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    schema_version: str = "1.0"
    case_id: str
    case_name: str = "untitled_case"
    case_type: CaseType = CaseType.unknown
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    caereflex_version: str = __version__
    workspace: WorkspaceInfo = Field(default_factory=WorkspaceInfo)
    inspection: InspectionInfo = Field(default_factory=InspectionInfo)
    detected_formats: list[str] = Field(default_factory=list)
    detected_tools: list[str] = Field(default_factory=list)
    physics_tags: list[str] = Field(default_factory=list)
    source_files: list[SourceFileRecord] = Field(default_factory=list)
    assets: list[EngineeringAsset] = Field(default_factory=list)
    solver_records: list[SolverRecord] = Field(default_factory=list)
    boundary_conditions: list[BoundaryConditionRecord] = Field(default_factory=list)
    materials: list[MaterialPropertyRecord] = Field(default_factory=list)
    numerical_settings: list[NumericalSettingsRecord] = Field(default_factory=list)
    result_fields: list[ResultFieldRecord] = Field(default_factory=list)
    literature_evidence: list[LiteratureEvidenceRecord] = Field(default_factory=list)
    literature_context: LiteratureContext = Field(default_factory=LiteratureContext)
    inspection_flags: list[InspectionFlag] = Field(default_factory=list)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    agent_summary: AgentSummary = Field(default_factory=AgentSummary)
    exports: list[ExportRecord] = Field(default_factory=list)
    contract_version: str | None = None
    inspection_profile: str | None = None
    case_manifest: dict[str, Any] | None = None
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    quantity_evidence: list[dict[str, Any]] = Field(default_factory=list)
    dimensional_checks: list[dict[str, Any]] = Field(default_factory=list)
    array_references: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdapterResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    adapter_name: str
    status: AdapterStatus
    case: ReflexCase | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
