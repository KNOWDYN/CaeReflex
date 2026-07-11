"""Backend-neutral spatial graph and coordinate-frame contracts for Gate 6A.

The contracts deliberately separate geometry, mesh, grouping and dataset entities.
Heavy coordinates and connectivity remain behind ArrayRef handles.
"""
from __future__ import annotations

import json
import math
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from caereflex.contracts import ArrayRef, CONTRACT_VERSION, SourceLocation
from caereflex.core.provenance import utc_now_iso

SPATIAL_GRAPH_VERSION = "1.0"
MAX_COMPACT_METADATA_BYTES = 64 * 1024
MAX_COMPACT_SEQUENCE_ITEMS = 256
_EPS = 1e-12


class SpatialContractError(ValueError):
    """Raised when compact spatial metadata violates the Gate 6A contract."""


class SpatialEvidenceStatus(str, Enum):
    explicit = "explicit"
    derived = "derived"
    user_supplied = "user_supplied"
    conflicted = "conflicted"
    unresolved = "unresolved"


class SpatialReviewStatus(str, Enum):
    unreviewed = "unreviewed"
    confirmed = "confirmed"
    rejected = "rejected"
    superseded = "superseded"


class CoordinateHandedness(str, Enum):
    right = "right"
    left = "left"
    unknown = "unknown"


class SpatialDomain(str, Enum):
    geometry = "geometry"
    mesh = "mesh"
    grouping = "grouping"
    dataset = "dataset"


class SpatialEntityKind(str, Enum):
    geometry_point = "geometry_point"
    geometry_curve = "geometry_curve"
    geometry_surface = "geometry_surface"
    geometry_shell = "geometry_shell"
    geometry_volume = "geometry_volume"
    mesh_node = "mesh_node"
    mesh_edge = "mesh_edge"
    mesh_face = "mesh_face"
    mesh_cell = "mesh_cell"
    patch = "patch"
    physical_group = "physical_group"
    region = "region"
    dataset_block = "dataset_block"


class SpatialRelationKind(str, Enum):
    contains = "contains"
    bounded_by = "bounded_by"
    adjacent_to = "adjacent_to"
    connected_to = "connected_to"
    discretises = "discretises"
    belongs_to = "belongs_to"
    carries_field = "carries_field"
    maps_to = "maps_to"
    derived_from = "derived_from"


class SpatialArrayRole(str, Enum):
    coordinates = "coordinates"
    connectivity = "connectivity"
    offsets = "offsets"
    cell_types = "cell_types"
    bounds = "bounds"
    normals = "normals"
    membership = "membership"
    field = "field"
    transform = "transform"
    other = "other"


class SpatialGraphStatus(str, Enum):
    draft = "draft"
    complete = "complete"
    conflicted = "conflicted"


_ENTITY_DOMAIN: dict[SpatialEntityKind, SpatialDomain] = {
    SpatialEntityKind.geometry_point: SpatialDomain.geometry,
    SpatialEntityKind.geometry_curve: SpatialDomain.geometry,
    SpatialEntityKind.geometry_surface: SpatialDomain.geometry,
    SpatialEntityKind.geometry_shell: SpatialDomain.geometry,
    SpatialEntityKind.geometry_volume: SpatialDomain.geometry,
    SpatialEntityKind.mesh_node: SpatialDomain.mesh,
    SpatialEntityKind.mesh_edge: SpatialDomain.mesh,
    SpatialEntityKind.mesh_face: SpatialDomain.mesh,
    SpatialEntityKind.mesh_cell: SpatialDomain.mesh,
    SpatialEntityKind.patch: SpatialDomain.grouping,
    SpatialEntityKind.physical_group: SpatialDomain.grouping,
    SpatialEntityKind.region: SpatialDomain.grouping,
    SpatialEntityKind.dataset_block: SpatialDomain.dataset,
}

_FIXED_TOPOLOGICAL_DIMENSION: dict[SpatialEntityKind, int] = {
    SpatialEntityKind.geometry_point: 0,
    SpatialEntityKind.geometry_curve: 1,
    SpatialEntityKind.geometry_surface: 2,
    SpatialEntityKind.geometry_shell: 2,
    SpatialEntityKind.geometry_volume: 3,
    SpatialEntityKind.mesh_node: 0,
    SpatialEntityKind.mesh_edge: 1,
    SpatialEntityKind.mesh_face: 2,
}


def _ensure_finite_scalar(value: float, label: str) -> float:
    converted = float(value)
    if not math.isfinite(converted):
        raise SpatialContractError(f"{label} must contain only finite values")
    return converted


def _validate_compact_value(value: Any, *, depth: int = 0) -> None:
    if depth > 8:
        raise SpatialContractError("compact metadata nesting exceeds 8 levels")
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise SpatialContractError("binary payloads are not allowed in compact spatial metadata")
    if isinstance(value, float) and not math.isfinite(value):
        raise SpatialContractError("non-finite numbers are not allowed in compact spatial metadata")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise SpatialContractError("compact metadata keys must be strings")
            _validate_compact_value(item, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_COMPACT_SEQUENCE_ITEMS:
            raise SpatialContractError(
                f"compact metadata sequences are limited to {MAX_COMPACT_SEQUENCE_ITEMS} items; "
                "use ArrayRef for heavy coordinates or connectivity"
            )
        for item in value:
            _validate_compact_value(item, depth=depth + 1)
        return
    if value is None or isinstance(value, (str, int, bool)):
        return
    raise SpatialContractError(f"unsupported compact metadata value type: {type(value).__name__}")


def validate_compact_metadata(value: dict[str, Any]) -> dict[str, Any]:
    _validate_compact_value(value)
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SpatialContractError(f"compact metadata is not strict JSON: {exc}") from exc
    if len(encoded) > MAX_COMPACT_METADATA_BYTES:
        raise SpatialContractError(
            f"compact metadata exceeds {MAX_COMPACT_METADATA_BYTES} bytes; use ArrayRef for heavy data"
        )
    return value


def _vector_norm(vector: tuple[float, float, float]) -> float:
    return math.sqrt(sum(component * component for component in vector))


def _cross(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _determinant3(basis: tuple[tuple[float, float, float], ...]) -> float:
    a, b, c = basis
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


class CompactSpatialModel(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def compact_metadata_only(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_compact_metadata(value)


class SpatialEvidenceRecord(CompactSpatialModel):
    evidence_id: str
    status: SpatialEvidenceStatus
    source_path: str | None = None
    source_location: SourceLocation | None = None
    parser: str | None = None
    method: str | None = None
    confidence: float | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def confidence_between_zero_and_one(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @field_validator("notes")
    @classmethod
    def bounded_notes(cls, value: list[str]) -> list[str]:
        if len(value) > 64:
            raise ValueError("evidence notes are limited to 64 entries")
        return value


class AxisAlignedBounds(CompactSpatialModel):
    coordinate_frame_id: str
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    active_dimensions: int = 3
    evidence_status: SpatialEvidenceStatus = SpatialEvidenceStatus.unresolved
    confidence: float | None = None

    @field_validator("active_dimensions")
    @classmethod
    def valid_active_dimensions(cls, value: int) -> int:
        if value not in {1, 2, 3}:
            raise ValueError("active_dimensions must be 1, 2, or 3")
        return value

    @field_validator("confidence")
    @classmethod
    def valid_confidence(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def finite_ordered_bounds(self) -> "AxisAlignedBounds":
        minimum = tuple(_ensure_finite_scalar(item, "minimum") for item in self.minimum)
        maximum = tuple(_ensure_finite_scalar(item, "maximum") for item in self.maximum)
        for index in range(self.active_dimensions):
            if minimum[index] > maximum[index]:
                raise ValueError("minimum bounds must not exceed maximum bounds")
        return self


class CoordinateFrame(CompactSpatialModel):
    frame_id: str
    name: str
    dimension: int
    origin: tuple[float, float, float] | None = None
    basis: tuple[tuple[float, float, float], ...] | None = None
    handedness: CoordinateHandedness = CoordinateHandedness.unknown
    length_unit: str | None = None
    length_unit_status: SpatialEvidenceStatus = SpatialEvidenceStatus.unresolved
    parent_frame_id: str | None = None
    transform_to_parent: tuple[
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
    ] | None = None
    evidence_status: SpatialEvidenceStatus = SpatialEvidenceStatus.unresolved
    confidence: float | None = None
    review_status: SpatialReviewStatus = SpatialReviewStatus.unreviewed
    source_backend: str | None = None
    source_asset_id: str | None = None
    evidence: list[SpatialEvidenceRecord] = Field(default_factory=list)

    @field_validator("dimension")
    @classmethod
    def dimension_between_one_and_three(cls, value: int) -> int:
        if value not in {1, 2, 3}:
            raise ValueError("coordinate-frame dimension must be 1, 2, or 3")
        return value

    @field_validator("confidence")
    @classmethod
    def confidence_between_zero_and_one(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def validate_resolution(self) -> "CoordinateFrame":
        status = SpatialEvidenceStatus(self.evidence_status)
        handedness = CoordinateHandedness(self.handedness)
        if self.parent_frame_id == self.frame_id:
            raise ValueError("coordinate frame cannot be its own parent")
        if self.origin is not None:
            tuple(_ensure_finite_scalar(item, "origin") for item in self.origin)
        if self.basis is not None:
            if len(self.basis) != self.dimension:
                raise ValueError("basis vector count must equal coordinate-frame dimension")
            vectors = tuple(
                tuple(_ensure_finite_scalar(item, "basis") for item in vector)
                for vector in self.basis
            )
            if any(_vector_norm(vector) <= _EPS for vector in vectors):
                raise ValueError("basis vectors must be non-zero")
            if self.dimension == 2 and _vector_norm(_cross(vectors[0], vectors[1])) <= _EPS:
                raise ValueError("2D basis vectors must be linearly independent")
            if self.dimension == 3:
                determinant = _determinant3(vectors)
                if abs(determinant) <= _EPS:
                    raise ValueError("3D basis vectors must be linearly independent")
                if handedness == CoordinateHandedness.right and determinant <= 0:
                    raise ValueError("right-handed frame requires a positive basis determinant")
                if handedness == CoordinateHandedness.left and determinant >= 0:
                    raise ValueError("left-handed frame requires a negative basis determinant")
        if self.dimension < 3 and handedness != CoordinateHandedness.unknown:
            raise ValueError("handedness is only declared for complete 3D bases")
        if status in {
            SpatialEvidenceStatus.explicit,
            SpatialEvidenceStatus.derived,
            SpatialEvidenceStatus.user_supplied,
        } and (self.origin is None or self.basis is None):
            raise ValueError("resolved coordinate frames require explicit origin and basis")
        unit_status = SpatialEvidenceStatus(self.length_unit_status)
        if self.length_unit is None and unit_status not in {
            SpatialEvidenceStatus.unresolved,
            SpatialEvidenceStatus.conflicted,
        }:
            raise ValueError("resolved length-unit status requires a length_unit value")
        if self.length_unit is not None and unit_status == SpatialEvidenceStatus.unresolved:
            raise ValueError("length_unit cannot be supplied with unresolved unit status")
        if self.transform_to_parent is not None and self.parent_frame_id is None:
            raise ValueError("transform_to_parent requires parent_frame_id")
        if self.parent_frame_id is not None and status in {
            SpatialEvidenceStatus.explicit,
            SpatialEvidenceStatus.derived,
            SpatialEvidenceStatus.user_supplied,
        } and self.transform_to_parent is None:
            raise ValueError("resolved child frames require transform_to_parent")
        if self.transform_to_parent is not None:
            for row in self.transform_to_parent:
                for item in row:
                    _ensure_finite_scalar(item, "transform_to_parent")
            if tuple(float(item) for item in self.transform_to_parent[3]) != (0.0, 0.0, 0.0, 1.0):
                raise ValueError("transform_to_parent must be an affine 4x4 transform")
        return self


class SpatialEntity(CompactSpatialModel):
    entity_id: str
    entity_kind: SpatialEntityKind
    domain: SpatialDomain | None = None
    name: str | None = None
    topological_dimension: int | None = None
    embedding_dimension: int | None = None
    coordinate_frame_id: str | None = None
    native_id: str | int | None = None
    source_backend: str | None = None
    source_asset_id: str | None = None
    source_path: str | None = None
    bounds: AxisAlignedBounds | None = None
    evidence_status: SpatialEvidenceStatus = SpatialEvidenceStatus.unresolved
    confidence: float | None = None
    review_status: SpatialReviewStatus = SpatialReviewStatus.unreviewed
    evidence: list[SpatialEvidenceRecord] = Field(default_factory=list)

    @field_validator("topological_dimension")
    @classmethod
    def valid_topological_dimension(cls, value: int | None) -> int | None:
        if value is not None and value not in {0, 1, 2, 3}:
            raise ValueError("topological_dimension must be between 0 and 3")
        return value

    @field_validator("embedding_dimension")
    @classmethod
    def valid_embedding_dimension(cls, value: int | None) -> int | None:
        if value is not None and value not in {1, 2, 3}:
            raise ValueError("embedding_dimension must be between 1 and 3")
        return value

    @field_validator("confidence")
    @classmethod
    def valid_confidence(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def canonical_entity_semantics(self) -> "SpatialEntity":
        kind = SpatialEntityKind(self.entity_kind)
        expected_domain = _ENTITY_DOMAIN[kind]
        if self.domain is not None and SpatialDomain(self.domain) != expected_domain:
            raise ValueError(f"{kind.value} belongs to the {expected_domain.value} domain")
        self.domain = expected_domain
        fixed_dimension = _FIXED_TOPOLOGICAL_DIMENSION.get(kind)
        if fixed_dimension is not None:
            if self.topological_dimension is None:
                self.topological_dimension = fixed_dimension
            elif self.topological_dimension != fixed_dimension:
                raise ValueError(
                    f"{kind.value} requires topological_dimension={fixed_dimension}"
                )
        if (
            self.topological_dimension is not None
            and self.embedding_dimension is not None
            and self.topological_dimension > self.embedding_dimension
        ):
            raise ValueError("topological_dimension cannot exceed embedding_dimension")
        if self.bounds is not None:
            if self.coordinate_frame_id is None:
                self.coordinate_frame_id = self.bounds.coordinate_frame_id
            elif self.bounds.coordinate_frame_id != self.coordinate_frame_id:
                raise ValueError("entity bounds must use the entity coordinate frame")
        return self


class SpatialRelation(CompactSpatialModel):
    relation_id: str
    relation_kind: SpatialRelationKind
    source_entity_id: str
    target_entity_id: str
    directed: bool = True
    evidence_status: SpatialEvidenceStatus = SpatialEvidenceStatus.unresolved
    confidence: float | None = None
    review_status: SpatialReviewStatus = SpatialReviewStatus.unreviewed
    evidence: list[SpatialEvidenceRecord] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def valid_confidence(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def relation_direction_and_identity(self) -> "SpatialRelation":
        if self.source_entity_id == self.target_entity_id:
            raise ValueError("spatial relations cannot be self-relations")
        kind = SpatialRelationKind(self.relation_kind)
        if kind in {SpatialRelationKind.adjacent_to, SpatialRelationKind.connected_to}:
            if self.directed:
                raise ValueError(f"{kind.value} relations must be undirected")
        elif not self.directed:
            raise ValueError(f"{kind.value} relations must be directed")
        return self


class SpatialArrayLink(CompactSpatialModel):
    link_id: str
    array_id: str
    role: SpatialArrayRole
    owner_entity_id: str | None = None
    owner_frame_id: str | None = None
    coordinate_frame_id: str | None = None
    array_uri: str | None = None
    checksum: str | None = None
    association: str | None = None
    component_semantics: list[str] = Field(default_factory=list)
    evidence_status: SpatialEvidenceStatus = SpatialEvidenceStatus.unresolved

    @model_validator(mode="after")
    def one_owner_and_safe_reference(self) -> "SpatialArrayLink":
        if (self.owner_entity_id is None) == (self.owner_frame_id is None):
            raise ValueError("SpatialArrayLink requires exactly one entity or frame owner")
        if self.array_uri is not None and not self.array_uri.startswith(
            "caereflex-artifact://sha256/"
        ):
            raise ValueError("spatial array links require content-addressed artefact URIs")
        if len(self.component_semantics) > 64:
            raise ValueError("component_semantics is limited to 64 entries")
        return self

    @classmethod
    def from_array_ref(
        cls,
        ref: ArrayRef,
        *,
        link_id: str,
        role: SpatialArrayRole,
        owner_entity_id: str | None = None,
        owner_frame_id: str | None = None,
        coordinate_frame_id: str | None = None,
        evidence_status: SpatialEvidenceStatus = SpatialEvidenceStatus.explicit,
        metadata: dict[str, Any] | None = None,
    ) -> "SpatialArrayLink":
        if not ref.array_id:
            raise ValueError("ArrayRef.array_id is required for spatial links")
        return cls(
            link_id=link_id,
            array_id=ref.array_id,
            role=role,
            owner_entity_id=owner_entity_id,
            owner_frame_id=owner_frame_id,
            coordinate_frame_id=coordinate_frame_id or ref.coordinate_frame_ref,
            array_uri=ref.uri,
            checksum=ref.checksum,
            association=ref.association,
            component_semantics=list(ref.component_names),
            evidence_status=evidence_status,
            metadata=metadata or {},
        )


class SpatialGraph(CompactSpatialModel):
    graph_id: str
    case_id: str
    graph_version: str = SPATIAL_GRAPH_VERSION
    contract_version: str = CONTRACT_VERSION
    name: str | None = None
    source_manifest_id: str | None = None
    default_coordinate_frame_id: str | None = None
    status: SpatialGraphStatus = SpatialGraphStatus.draft
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class SpatialGraphSnapshot(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    graph: SpatialGraph
    coordinate_frames: list[CoordinateFrame] = Field(default_factory=list)
    entities: list[SpatialEntity] = Field(default_factory=list)
    relations: list[SpatialRelation] = Field(default_factory=list)
    array_links: list[SpatialArrayLink] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_snapshot_references(self) -> "SpatialGraphSnapshot":
        frame_ids = [item.frame_id for item in self.coordinate_frames]
        entity_ids = [item.entity_id for item in self.entities]
        relation_ids = [item.relation_id for item in self.relations]
        link_ids = [item.link_id for item in self.array_links]
        for label, values in (
            ("coordinate frame", frame_ids),
            ("entity", entity_ids),
            ("relation", relation_ids),
            ("array link", link_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} IDs are not allowed")
        frame_set = set(frame_ids)
        entity_set = set(entity_ids)
        if (
            self.graph.default_coordinate_frame_id is not None
            and self.graph.default_coordinate_frame_id not in frame_set
        ):
            raise ValueError("default coordinate frame is absent from the snapshot")
        for frame in self.coordinate_frames:
            if frame.parent_frame_id is not None and frame.parent_frame_id not in frame_set:
                raise ValueError(f"frame parent is absent from snapshot: {frame.parent_frame_id}")
        self._validate_frame_cycles({item.frame_id: item.parent_frame_id for item in self.coordinate_frames})
        for entity in self.entities:
            if entity.coordinate_frame_id is not None and entity.coordinate_frame_id not in frame_set:
                raise ValueError(
                    f"entity coordinate frame is absent from snapshot: {entity.coordinate_frame_id}"
                )
        for relation in self.relations:
            if relation.source_entity_id not in entity_set or relation.target_entity_id not in entity_set:
                raise ValueError("relation endpoints must exist in the same snapshot")
        for link in self.array_links:
            if link.owner_entity_id is not None and link.owner_entity_id not in entity_set:
                raise ValueError("array-link entity owner is absent from snapshot")
            if link.owner_frame_id is not None and link.owner_frame_id not in frame_set:
                raise ValueError("array-link frame owner is absent from snapshot")
            if link.coordinate_frame_id is not None and link.coordinate_frame_id not in frame_set:
                raise ValueError("array-link coordinate frame is absent from snapshot")
        return self

    @staticmethod
    def _validate_frame_cycles(parent_by_frame: dict[str, str | None]) -> None:
        for frame_id in parent_by_frame:
            seen: set[str] = set()
            current: str | None = frame_id
            while current is not None:
                if current in seen:
                    raise ValueError("coordinate-frame parent cycle detected")
                seen.add(current)
                current = parent_by_frame.get(current)


class SpatialGraphRef(BaseModel):
    graph_id: str
    store_uri: str
    graph_version: str
    contract_version: str
    default_coordinate_frame_id: str | None = None
    frame_count: int = 0
    entity_count: int = 0
    relation_count: int = 0
    array_link_count: int = 0
    updated_at: str
