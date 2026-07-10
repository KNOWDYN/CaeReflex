"""Stable contracts for scalable CaeReflex inspection workflows.

The contracts are intentionally backend-neutral. Native parser objects, unit-library
objects, and large numerical arrays must not leak into serialized ReflexCase data.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from caereflex.core.provenance import utc_now_iso

CONTRACT_VERSION = "2.0-alpha.1"


class EvidenceState(str, Enum):
    exactly_parsed = "exactly_parsed"
    natively_decoded = "natively_decoded"
    heuristically_parsed = "heuristically_parsed"
    inferred = "inferred"
    user_supplied = "user_supplied"
    conflicted = "conflicted"
    unsupported = "unsupported"
    unavailable = "unavailable"


class InspectionProfile(str, Enum):
    catalog = "catalog"
    standard = "standard"
    deep = "deep"
    forensic = "forensic"


class DiagnosticSeverity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"


class ManifestRole(str, Enum):
    geometry = "geometry"
    mesh = "mesh"
    solver_control = "solver_control"
    solver_dictionary = "solver_dictionary"
    initial_field = "initial_field"
    time_field = "time_field"
    result = "result"
    log = "log"
    literature = "literature"
    directory = "directory"
    unknown = "unknown"


class SourceLocation(BaseModel):
    line_start: int | None = None
    line_end: int | None = None
    byte_start: int | None = None
    byte_end: int | None = None


class EvidenceValue(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    value: Any = None
    raw_value: str | None = None
    source_path: str | None = None
    source_location: SourceLocation | None = None
    parser: str | None = None
    extraction_method: str | None = None
    evidence_state: EvidenceState = EvidenceState.unavailable
    confidence: float | None = None
    warnings: list[str] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value


class QuantityEvidence(EvidenceValue):
    magnitude: float | int | list[float] | None = None
    unit: str | None = None
    dimension_vector: tuple[float, float, float, float, float, float, float] | None = None
    quantity_kind: str | None = None
    normalized_magnitude: float | int | list[float] | None = None
    normalized_unit: str | None = None


class ArrayRef(BaseModel):
    uri: str
    format: str
    shape: tuple[int, ...]
    dtype: str
    chunks: tuple[int, ...] | None = None
    checksum: str | None = None
    selection_capabilities: list[str] = Field(default_factory=list)


class DiagnosticEvent(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    code: str
    severity: DiagnosticSeverity
    message: str
    source_path: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    parser: str | None = None
    fallback_used: str | None = None
    information_lost: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class ManifestEntry(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    path: str
    is_dir: bool = False
    role: ManifestRole = ManifestRole.unknown
    suffix: str | None = None
    size_bytes: int | None = None
    modified_ns: int | None = None
    depth: int = 0
    format_hint: str | None = None
    case_hint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InspectionBudget(BaseModel):
    max_files: int = 500
    max_depth: int = 3
    max_bytes_read: int = 25 * 1024 * 1024
    max_wall_time_seconds: float = 30.0
    max_time_steps: int = 50
    sample_cells: int = 10_000
    sample_points: int = 10_000

    @field_validator("max_files", "max_depth", "max_bytes_read", "max_time_steps", "sample_cells", "sample_points")
    @classmethod
    def non_negative_ints(cls, value: int) -> int:
        if value < 0:
            raise ValueError("inspection budget values must be non-negative")
        return value

    @field_validator("max_wall_time_seconds")
    @classmethod
    def positive_wall_time(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("max_wall_time_seconds must be positive")
        return value


class CaseManifest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    contract_version: str = CONTRACT_VERSION
    manifest_id: str
    root_uri: str
    storage_protocol: str = "file"
    created_at: str = Field(default_factory=utc_now_iso)
    profile: InspectionProfile = InspectionProfile.catalog
    entries: list[ManifestEntry] = Field(default_factory=list)
    detected_formats: list[str] = Field(default_factory=list)
    case_hints: list[str] = Field(default_factory=list)
    bytes_catalogued: int = 0
    truncated: bool = False
    limits_reached: list[str] = Field(default_factory=list)
    diagnostics: list[DiagnosticEvent] = Field(default_factory=list)
    signature: str | None = None


class AdapterCapabilities(BaseModel):
    plugin_id: str
    plugin_version: str
    schema_range: str = ">=1.0,<3.0"
    formats: list[str] = Field(default_factory=list)
    geometry_support: str = "none"
    topology_support: str = "none"
    field_support: str = "none"
    time_series_support: bool = False
    units_support: str = "none"
    fallback_modes: list[str] = Field(default_factory=list)
    optional_dependencies: list[str] = Field(default_factory=list)
    licence: str = "unknown"
    read_only: bool = True
    requires_network: bool = False
    requires_source_execution: bool = False


class ProbeResult(BaseModel):
    plugin_id: str
    supported: bool
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    diagnostics: list[DiagnosticEvent] = Field(default_factory=list)

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("probe score must be between 0 and 1")
        return value


class InspectionPlan(BaseModel):
    plugin_id: str
    profile: InspectionProfile
    selected_paths: list[str] = Field(default_factory=list)
    budget: InspectionBudget = Field(default_factory=InspectionBudget)
    diagnostics: list[DiagnosticEvent] = Field(default_factory=list)


@runtime_checkable
class AdapterPlugin(Protocol):
    """Protocol implemented by separately distributed CaeReflex adapters."""

    plugin_id: str
    plugin_version: str

    def capabilities(self) -> AdapterCapabilities: ...
    def probe(self, manifest: CaseManifest) -> ProbeResult: ...
    def plan(
        self,
        manifest: CaseManifest,
        profile: InspectionProfile,
        budget: InspectionBudget,
    ) -> InspectionPlan: ...
