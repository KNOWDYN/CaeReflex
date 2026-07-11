"""Backend-to-graph mapping for native OpenFOAM, Gmsh and VTK evidence.

Gate 6B translates bounded Gate 5 execution summaries and ArrayRef handles into the
canonical Gate 6A spatial graph. It does not compare formats, compose coordinate
frames, infer adjacency, or materialise heavy arrays.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from caereflex.contracts import ArrayRef, InspectionExecutionResult
from caereflex.core.provenance import utc_now_iso
from caereflex.spatial.contracts import (
    AxisAlignedBounds,
    CoordinateFrame,
    CoordinateHandedness,
    SpatialArrayLink,
    SpatialArrayRole,
    SpatialEntity,
    SpatialEntityKind,
    SpatialEvidenceRecord,
    SpatialEvidenceStatus,
    SpatialGraph,
    SpatialGraphSnapshot,
    SpatialGraphStatus,
    SpatialRelation,
    SpatialRelationKind,
)
from caereflex.spatial.service import attach_spatial_graph_ref
from caereflex.spatial.store import SpatialStore

SPATIAL_MAPPING_VERSION = "caereflex.spatial-mapping/1.0"
SUPPORTED_MAPPING_BACKENDS = frozenset({"openfoam.native", "gmsh.native", "vtk.native"})


class SpatialMappingError(RuntimeError):
    """Raised when an execution result cannot be mapped without inventing evidence."""


class SpatialMappingDiagnostic(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    code: str
    message: str
    backend_id: str
    source_path: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SpatialMappingResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    mapping_version: str = SPATIAL_MAPPING_VERSION
    backend_id: str
    execution_id: str
    graph_id: str
    snapshot: SpatialGraphSnapshot
    mapped_array_ids: list[str] = Field(default_factory=list)
    skipped_array_ids: list[str] = Field(default_factory=list)
    diagnostics: list[SpatialMappingDiagnostic] = Field(default_factory=list)

    def compact_report(self) -> dict[str, Any]:
        return {
            "mapping_version": self.mapping_version,
            "backend_id": self.backend_id,
            "execution_id": self.execution_id,
            "graph_id": self.graph_id,
            "frame_count": len(self.snapshot.coordinate_frames),
            "entity_count": len(self.snapshot.entities),
            "relation_count": len(self.snapshot.relations),
            "array_link_count": len(self.snapshot.array_links),
            "mapped_array_count": len(self.mapped_array_ids),
            "skipped_array_count": len(self.skipped_array_ids),
            "diagnostics": [item.model_dump(mode="json") for item in self.diagnostics],
        }


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _native_dimension(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed in {0, 1, 2, 3} else None


def _dimension(value: Any, default: int = 3) -> int:
    parsed = _native_dimension(value)
    return parsed if parsed in {1, 2, 3} else default


def _evidence(
    *,
    backend_id: str,
    source_path: str | None,
    method: str,
    status: SpatialEvidenceStatus = SpatialEvidenceStatus.explicit,
    confidence: float = 1.0,
    metadata: dict[str, Any] | None = None,
) -> SpatialEvidenceRecord:
    return SpatialEvidenceRecord(
        evidence_id=_stable_id("evidence", backend_id, source_path or "", method),
        status=status,
        source_path=source_path,
        parser=backend_id,
        method=method,
        confidence=confidence,
        metadata=metadata or {},
    )


def _bounds(
    raw: Any,
    *,
    frame_id: str,
    active_dimensions: int,
    status: SpatialEvidenceStatus = SpatialEvidenceStatus.explicit,
) -> AxisAlignedBounds | None:
    if not isinstance(raw, list) or len(raw) < 3:
        return None
    minimum: list[float] = []
    maximum: list[float] = []
    for axis in raw[:3]:
        if not isinstance(axis, (list, tuple)) or len(axis) != 2:
            return None
        low = _finite_number(axis[0])
        high = _finite_number(axis[1])
        if low is None or high is None or low > high:
            return None
        minimum.append(low)
        maximum.append(high)
    return AxisAlignedBounds(
        coordinate_frame_id=frame_id,
        minimum=tuple(minimum),
        maximum=tuple(maximum),
        active_dimensions=active_dimensions,
        evidence_status=status,
        confidence=1.0 if status == SpatialEvidenceStatus.explicit else None,
    )


def _unresolved_frame(
    *,
    frame_id: str,
    name: str,
    dimension: int,
    backend_id: str,
    asset_id: str | None,
    source_path: str | None,
) -> CoordinateFrame:
    return CoordinateFrame(
        frame_id=frame_id,
        name=name,
        dimension=_dimension(dimension),
        evidence_status=SpatialEvidenceStatus.unresolved,
        length_unit_status=SpatialEvidenceStatus.unresolved,
        handedness=CoordinateHandedness.unknown,
        source_backend=backend_id,
        source_asset_id=asset_id,
        evidence=[
            _evidence(
                backend_id=backend_id,
                source_path=source_path,
                method="native-coordinate-frame-inventory",
                status=SpatialEvidenceStatus.unresolved,
                confidence=0.0,
                metadata={
                    "origin": "not asserted",
                    "basis": "not asserted",
                    "length_unit": "not asserted",
                },
            )
        ],
    )


def _vtk_frame(
    *,
    frame_id: str,
    file_summary: dict[str, Any],
    backend_id: str,
    asset_id: str,
) -> CoordinateFrame:
    source_path = str(file_summary.get("source_path") or "") or None
    dimension = _dimension(file_summary.get("dimension"), 3)
    origin_raw = file_summary.get("origin")
    direction_raw = file_summary.get("direction")
    origin: tuple[float, float, float] | None = None
    basis: tuple[tuple[float, float, float], ...] | None = None
    if isinstance(origin_raw, (list, tuple)) and len(origin_raw) >= 3:
        values = tuple(_finite_number(item) for item in origin_raw[:3])
        if all(item is not None for item in values):
            origin = tuple(float(item) for item in values)  # type: ignore[arg-type]
    rows: list[list[Any]] = []
    if isinstance(direction_raw, (list, tuple)):
        if len(direction_raw) == 9 and not any(isinstance(item, (list, tuple)) for item in direction_raw):
            rows = [list(direction_raw[index:index + 3]) for index in range(0, 9, 3)]
        elif len(direction_raw) >= 3 and all(isinstance(item, (list, tuple)) for item in direction_raw[:3]):
            rows = [list(item[:3]) for item in direction_raw[:3]]
    if rows:
        converted_rows: list[tuple[float, float, float]] = []
        for row in rows[:dimension]:
            values = tuple(_finite_number(item) for item in row)
            if len(values) != 3 or any(item is None for item in values):
                converted_rows = []
                break
            converted_rows.append(tuple(float(item) for item in values))  # type: ignore[arg-type]
        if len(converted_rows) == dimension:
            basis = tuple(converted_rows)
    if origin is None or basis is None:
        return _unresolved_frame(
            frame_id=frame_id,
            name=f"VTK dataset frame: {source_path or asset_id}",
            dimension=dimension,
            backend_id=backend_id,
            asset_id=asset_id,
            source_path=source_path,
        )
    handedness = CoordinateHandedness.unknown
    if dimension == 3:
        determinant = (
            basis[0][0] * (basis[1][1] * basis[2][2] - basis[1][2] * basis[2][1])
            - basis[0][1] * (basis[1][0] * basis[2][2] - basis[1][2] * basis[2][0])
            + basis[0][2] * (basis[1][0] * basis[2][1] - basis[1][1] * basis[2][0])
        )
        if abs(determinant) > 1e-12:
            handedness = CoordinateHandedness.right if determinant > 0 else CoordinateHandedness.left
    return CoordinateFrame(
        frame_id=frame_id,
        name=f"VTK dataset frame: {source_path or asset_id}",
        dimension=dimension,
        origin=origin,
        basis=basis,
        handedness=handedness,
        evidence_status=SpatialEvidenceStatus.explicit,
        confidence=1.0,
        length_unit_status=SpatialEvidenceStatus.unresolved,
        source_backend=backend_id,
        source_asset_id=asset_id,
        evidence=[
            _evidence(
                backend_id=backend_id,
                source_path=source_path,
                method="vtk-origin-and-direction",
                metadata={"length_unit": "unresolved"},
            )
        ],
    )


def _entity_kind_for_dimension(dimension: int | None, *, geometry: bool) -> SpatialEntityKind:
    if geometry:
        return {
            0: SpatialEntityKind.geometry_point,
            1: SpatialEntityKind.geometry_curve,
            2: SpatialEntityKind.geometry_surface,
            3: SpatialEntityKind.geometry_volume,
        }.get(dimension, SpatialEntityKind.geometry_volume)
    return {
        0: SpatialEntityKind.mesh_cell,
        1: SpatialEntityKind.mesh_edge,
        2: SpatialEntityKind.mesh_face,
        3: SpatialEntityKind.mesh_cell,
    }.get(dimension, SpatialEntityKind.mesh_cell)


def _add_entity(collection: dict[str, SpatialEntity], entity: SpatialEntity) -> SpatialEntity:
    collection.setdefault(entity.entity_id, entity)
    return collection[entity.entity_id]


def _add_relation(collection: dict[str, SpatialRelation], relation: SpatialRelation) -> None:
    collection.setdefault(relation.relation_id, relation)


def _contains(
    relations: dict[str, SpatialRelation],
    *,
    backend_id: str,
    source: SpatialEntity,
    target: SpatialEntity,
    source_path: str | None,
    kind: SpatialRelationKind = SpatialRelationKind.contains,
    metadata: dict[str, Any] | None = None,
) -> None:
    _add_relation(
        relations,
        SpatialRelation(
            relation_id=_stable_id("relation", backend_id, kind.value, source.entity_id, target.entity_id),
            relation_kind=kind,
            source_entity_id=source.entity_id,
            target_entity_id=target.entity_id,
            directed=True,
            evidence_status=SpatialEvidenceStatus.explicit,
            confidence=1.0,
            evidence=[
                _evidence(
                    backend_id=backend_id,
                    source_path=source_path,
                    method=f"native-{kind.value}",
                    metadata=metadata,
                )
            ],
        ),
    )


def _array_role(ref: ArrayRef) -> SpatialArrayRole:
    role = str(ref.metadata.get("role") or ref.metadata.get("name") or "").lower()
    if ("point" in role and ("mesh" in role or "geo" in role)) or role == "points":
        return SpatialArrayRole.coordinates
    if "coordinate_axis" in role:
        return SpatialArrayRole.coordinates
    if "connectivity" in role:
        return SpatialArrayRole.connectivity
    if "offset" in role:
        return SpatialArrayRole.offsets
    if "cell_type" in role or "element_type" in role:
        return SpatialArrayRole.cell_types
    if any(token in role for token in ("field", "data_array", "internal_field")):
        return SpatialArrayRole.field
    if any(token in role for token in ("owner", "neighbour", "membership", "physical", "entity_tag", "tags")):
        return SpatialArrayRole.membership
    if "normal" in role:
        return SpatialArrayRole.normals
    if "bound" in role:
        return SpatialArrayRole.bounds
    if "transform" in role:
        return SpatialArrayRole.transform
    return SpatialArrayRole.other


def _link_array(
    links: dict[str, SpatialArrayLink],
    *,
    ref: ArrayRef,
    owner_entity_id: str,
    frame_id: str | None,
    backend_id: str,
    mapping_reason: str,
) -> None:
    if not ref.array_id:
        return
    role = _array_role(ref)
    link = SpatialArrayLink.from_array_ref(
        ref,
        link_id=_stable_id("arraylink", backend_id, ref.array_id, owner_entity_id, role.value),
        role=role,
        owner_entity_id=owner_entity_id,
        coordinate_frame_id=frame_id,
        evidence_status=SpatialEvidenceStatus.explicit,
        metadata={
            "mapping_reason": mapping_reason,
            "source_asset_id": ref.source_asset_id,
            "native_role": ref.metadata.get("role"),
            "time_index": ref.time_index,
        },
    )
    links.setdefault(link.link_id, link)


def _base_graph(
    *,
    case_id: str,
    backend_id: str,
    execution_id: str,
    source_manifest_id: str | None,
    graph_id: str | None,
) -> SpatialGraph:
    resolved_graph_id = graph_id or _stable_id(
        "graph", case_id, backend_id, source_manifest_id or execution_id
    )
    now = utc_now_iso()
    return SpatialGraph(
        graph_id=resolved_graph_id,
        case_id=case_id,
        name=f"{backend_id} spatial evidence",
        source_manifest_id=source_manifest_id,
        status=SpatialGraphStatus.draft,
        created_at=now,
        updated_at=now,
        metadata={
            "mapping_version": SPATIAL_MAPPING_VERSION,
            "source_backend": backend_id,
            "execution_id": execution_id,
            "cross_format_equivalence_asserted": False,
        },
    )


def _backend_summary(result: InspectionExecutionResult) -> dict[str, Any]:
    backend_result = result.metadata.get("backend_result") if isinstance(result.metadata, dict) else None
    if not isinstance(backend_result, dict) or not isinstance(backend_result.get("summary"), dict):
        raise SpatialMappingError("Execution result does not contain a backend summary object")
    return backend_result["summary"]


def _map_openfoam(
    *,
    graph: SpatialGraph,
    result: InspectionExecutionResult,
    summary: dict[str, Any],
) -> SpatialMappingResult:
    backend_id = result.backend_id
    frame_id = _stable_id("frame", graph.graph_id, "openfoam-case")
    mesh = summary.get("mesh") if isinstance(summary.get("mesh"), dict) else {}
    frame = _unresolved_frame(
        frame_id=frame_id,
        name="OpenFOAM case coordinates",
        dimension=3,
        backend_id=backend_id,
        asset_id="asset_openfoam_mesh",
        source_path="constant/polyMesh/points",
    )
    entities: dict[str, SpatialEntity] = {}
    relations: dict[str, SpatialRelation] = {}
    links: dict[str, SpatialArrayLink] = {}
    root = _add_entity(
        entities,
        SpatialEntity(
            entity_id=_stable_id("entity", graph.graph_id, "openfoam-case"),
            entity_kind=SpatialEntityKind.dataset_block,
            name="OpenFOAM case",
            embedding_dimension=3,
            coordinate_frame_id=frame_id,
            source_backend=backend_id,
            source_asset_id="asset_openfoam_case",
            evidence_status=SpatialEvidenceStatus.explicit,
            confidence=1.0,
            metadata={
                "format": "OpenFOAM",
                "complete_topology": bool(mesh.get("complete_topology")),
                "time_directories": list(summary.get("time_directories") or [])[:256],
                "field_count": int(summary.get("field_count") or 0),
            },
            evidence=[_evidence(backend_id=backend_id, source_path=None, method="openfoam-native-summary")],
        ),
    )
    node_entity: SpatialEntity | None = None
    face_entity: SpatialEntity | None = None
    cell_entity: SpatialEntity | None = None
    if int(mesh.get("points") or 0) > 0:
        node_entity = _add_entity(
            entities,
            SpatialEntity(
                entity_id=_stable_id("entity", graph.graph_id, "openfoam-nodes"),
                entity_kind=SpatialEntityKind.mesh_node,
                name="OpenFOAM mesh nodes",
                embedding_dimension=3,
                coordinate_frame_id=frame_id,
                source_backend=backend_id,
                source_asset_id="asset_openfoam_mesh",
                source_path="constant/polyMesh/points",
                bounds=_bounds(mesh.get("bounds"), frame_id=frame_id, active_dimensions=3),
                evidence_status=SpatialEvidenceStatus.explicit,
                confidence=1.0,
                metadata={"aggregate": True, "count": int(mesh.get("points") or 0)},
                evidence=[_evidence(backend_id=backend_id, source_path="constant/polyMesh/points", method="native-node-count")],
            ),
        )
        _contains(relations, backend_id=backend_id, source=root, target=node_entity, source_path="constant/polyMesh/points")
    if int(mesh.get("faces") or 0) > 0:
        face_entity = _add_entity(
            entities,
            SpatialEntity(
                entity_id=_stable_id("entity", graph.graph_id, "openfoam-faces"),
                entity_kind=SpatialEntityKind.mesh_face,
                name="OpenFOAM mesh faces",
                embedding_dimension=3,
                coordinate_frame_id=frame_id,
                source_backend=backend_id,
                source_asset_id="asset_openfoam_mesh",
                source_path="constant/polyMesh/faces",
                evidence_status=SpatialEvidenceStatus.explicit,
                confidence=1.0,
                metadata={
                    "aggregate": True,
                    "count": int(mesh.get("faces") or 0),
                    "internal_face_count": int(mesh.get("internal_faces") or 0),
                },
                evidence=[_evidence(backend_id=backend_id, source_path="constant/polyMesh/faces", method="native-face-count")],
            ),
        )
        _contains(relations, backend_id=backend_id, source=root, target=face_entity, source_path="constant/polyMesh/faces")
    if int(mesh.get("cells") or 0) > 0:
        cell_entity = _add_entity(
            entities,
            SpatialEntity(
                entity_id=_stable_id("entity", graph.graph_id, "openfoam-cells"),
                entity_kind=SpatialEntityKind.mesh_cell,
                name="OpenFOAM mesh cells",
                topological_dimension=3,
                embedding_dimension=3,
                coordinate_frame_id=frame_id,
                source_backend=backend_id,
                source_asset_id="asset_openfoam_mesh",
                source_path="constant/polyMesh/owner",
                evidence_status=SpatialEvidenceStatus.explicit,
                confidence=1.0,
                metadata={"aggregate": True, "count": int(mesh.get("cells") or 0)},
                evidence=[_evidence(backend_id=backend_id, source_path="constant/polyMesh/owner", method="native-cell-count")],
            ),
        )
        _contains(relations, backend_id=backend_id, source=root, target=cell_entity, source_path="constant/polyMesh/owner")
    for index, patch in enumerate(summary.get("patches") or []):
        if not isinstance(patch, dict):
            continue
        patch_name = str(patch.get("name") or f"patch_{index}")
        entity = _add_entity(
            entities,
            SpatialEntity(
                entity_id=_stable_id("entity", graph.graph_id, "openfoam-patch", patch_name, index),
                entity_kind=SpatialEntityKind.patch,
                name=patch_name,
                topological_dimension=2,
                embedding_dimension=3,
                coordinate_frame_id=frame_id,
                native_id=patch_name,
                source_backend=backend_id,
                source_asset_id="asset_openfoam_mesh",
                source_path="constant/polyMesh/boundary",
                evidence_status=SpatialEvidenceStatus.explicit,
                confidence=1.0,
                metadata={
                    "patch_type": patch.get("type"),
                    "physical_type": patch.get("physical_type"),
                    "start_face": patch.get("start_face"),
                    "face_count": patch.get("n_faces"),
                },
                evidence=[_evidence(backend_id=backend_id, source_path="constant/polyMesh/boundary", method="native-boundary-entry")],
            ),
        )
        _contains(relations, backend_id=backend_id, source=root, target=entity, source_path="constant/polyMesh/boundary")
        _contains(relations, backend_id=backend_id, source=entity, target=root, source_path="constant/polyMesh/boundary", kind=SpatialRelationKind.belongs_to)
    arrays = {item.array_id: item for item in result.arrays if item.array_id}
    mapped: set[str] = set()
    for array_id, ref in arrays.items():
        native_role = str(ref.metadata.get("role") or "")
        if native_role == "mesh_points" and node_entity is not None:
            owner = node_entity
        elif native_role in {"face_offsets", "face_connectivity", "owner", "neighbour"} and face_entity is not None:
            owner = face_entity
        elif native_role == "internal_field" and cell_entity is not None:
            owner = cell_entity
        else:
            owner = root
        _link_array(
            links,
            ref=ref,
            owner_entity_id=owner.entity_id,
            frame_id=frame_id,
            backend_id=backend_id,
            mapping_reason=f"openfoam:{native_role or ref.association or 'unclassified'}",
        )
        mapped.add(array_id)
    graph.default_coordinate_frame_id = frame_id
    graph.status = SpatialGraphStatus.complete
    snapshot = SpatialGraphSnapshot(
        graph=graph,
        coordinate_frames=[frame],
        entities=sorted(entities.values(), key=lambda item: item.entity_id),
        relations=sorted(relations.values(), key=lambda item: item.relation_id),
        array_links=sorted(links.values(), key=lambda item: item.link_id),
    )
    return SpatialMappingResult(
        backend_id=backend_id,
        execution_id=result.execution_id,
        graph_id=graph.graph_id,
        snapshot=snapshot,
        mapped_array_ids=sorted(mapped),
        skipped_array_ids=sorted(set(arrays) - mapped),
    )


def _gmsh_geometry_kind(item: dict[str, Any]) -> SpatialEntityKind:
    kind = str(item.get("kind") or "").lower()
    if kind == "surface_loop":
        return SpatialEntityKind.geometry_shell
    if kind == "curve_loop":
        return SpatialEntityKind.geometry_curve
    return _entity_kind_for_dimension(_native_dimension(item.get("dimension")), geometry=True)


def _map_gmsh(
    *,
    graph: SpatialGraph,
    result: InspectionExecutionResult,
    summary: dict[str, Any],
) -> SpatialMappingResult:
    backend_id = result.backend_id
    arrays = {item.array_id: item for item in result.arrays if item.array_id}
    entities: dict[str, SpatialEntity] = {}
    relations: dict[str, SpatialRelation] = {}
    links: dict[str, SpatialArrayLink] = {}
    frames: dict[str, CoordinateFrame] = {}
    root_by_asset: dict[str, SpatialEntity] = {}
    node_by_asset: dict[str, SpatialEntity] = {}
    cell_by_asset_dimension: dict[tuple[str, int], SpatialEntity] = {}
    frame_by_asset: dict[str, str] = {}
    geometry_by_native: dict[tuple[str, int, str], SpatialEntity] = {}
    mapped: set[str] = set()
    diagnostics: list[SpatialMappingDiagnostic] = []
    files = summary.get("files") if isinstance(summary.get("files"), list) else []
    for index, file_summary in enumerate(files, start=1):
        if not isinstance(file_summary, dict):
            continue
        source_path = str(file_summary.get("source_path") or f"gmsh_source_{index}")
        asset_id = f"asset_gmsh_{index}"
        dimension = _dimension(file_summary.get("dimension"), 3)
        frame_id = _stable_id("frame", graph.graph_id, asset_id, source_path)
        frame_by_asset[asset_id] = frame_id
        frames[frame_id] = _unresolved_frame(
            frame_id=frame_id,
            name=f"Gmsh model frame: {source_path}",
            dimension=dimension,
            backend_id=backend_id,
            asset_id=asset_id,
            source_path=source_path,
        )
        status = str(file_summary.get("status") or "unresolved")
        evidence_status = SpatialEvidenceStatus.explicit if status == "decoded" else SpatialEvidenceStatus.unresolved
        root = _add_entity(
            entities,
            SpatialEntity(
                entity_id=_stable_id("entity", graph.graph_id, asset_id, "root"),
                entity_kind=SpatialEntityKind.dataset_block,
                name=source_path,
                embedding_dimension=dimension,
                coordinate_frame_id=frame_id,
                native_id=source_path,
                source_backend=backend_id,
                source_asset_id=asset_id,
                source_path=source_path,
                bounds=_bounds(file_summary.get("bounds"), frame_id=frame_id, active_dimensions=dimension, status=evidence_status),
                evidence_status=evidence_status,
                confidence=1.0 if evidence_status == SpatialEvidenceStatus.explicit else None,
                metadata={
                    "gmsh_kind": file_summary.get("kind"),
                    "reader": file_summary.get("reader"),
                    "status": status,
                    "node_count": file_summary.get("node_count") or file_summary.get("point_count"),
                    "element_count": file_summary.get("element_count"),
                    "mesh_format_version": file_summary.get("mesh_format_version"),
                    "coordinate_units": file_summary.get("coordinate_units", "unresolved"),
                },
                evidence=[
                    _evidence(
                        backend_id=backend_id,
                        source_path=source_path,
                        method="gmsh-file-summary",
                        status=evidence_status,
                        confidence=1.0 if evidence_status == SpatialEvidenceStatus.explicit else 0.0,
                    )
                ],
            ),
        )
        root_by_asset[asset_id] = root
        point_count = int(file_summary.get("node_count") or file_summary.get("point_count") or 0)
        if point_count > 0:
            node_kind = SpatialEntityKind.geometry_point if file_summary.get("kind") == "geo_declarations" else SpatialEntityKind.mesh_node
            node_entity = _add_entity(
                entities,
                SpatialEntity(
                    entity_id=_stable_id("entity", graph.graph_id, asset_id, "points"),
                    entity_kind=node_kind,
                    name=f"{source_path} points",
                    embedding_dimension=dimension,
                    coordinate_frame_id=frame_id,
                    source_backend=backend_id,
                    source_asset_id=asset_id,
                    source_path=source_path,
                    bounds=_bounds(file_summary.get("bounds"), frame_id=frame_id, active_dimensions=dimension, status=evidence_status),
                    evidence_status=evidence_status,
                    confidence=1.0 if evidence_status == SpatialEvidenceStatus.explicit else None,
                    metadata={"aggregate": True, "count": point_count},
                    evidence=[_evidence(backend_id=backend_id, source_path=source_path, method="gmsh-point-count", status=evidence_status)],
                ),
            )
            node_by_asset[asset_id] = node_entity
            _contains(relations, backend_id=backend_id, source=root, target=node_entity, source_path=source_path)
        for type_index, cell_type in enumerate(file_summary.get("cell_types") or []):
            if not isinstance(cell_type, dict):
                continue
            cell_dimension = _native_dimension(cell_type.get("dimension"))
            if cell_dimension is None:
                cell_dimension = dimension
            native_type = cell_type.get("gmsh_type") if "gmsh_type" in cell_type else cell_type.get("name")
            kind = _entity_kind_for_dimension(cell_dimension, geometry=False)
            entity = _add_entity(
                entities,
                SpatialEntity(
                    entity_id=_stable_id("entity", graph.graph_id, asset_id, "cell-type", native_type, type_index),
                    entity_kind=kind,
                    name=str(cell_type.get("name") or f"Gmsh type {native_type}"),
                    topological_dimension=cell_dimension,
                    embedding_dimension=dimension,
                    coordinate_frame_id=frame_id,
                    native_id=str(native_type),
                    source_backend=backend_id,
                    source_asset_id=asset_id,
                    source_path=source_path,
                    evidence_status=SpatialEvidenceStatus.explicit,
                    confidence=1.0,
                    metadata={"aggregate": True, "count": int(cell_type.get("count") or 0), "gmsh_type": cell_type.get("gmsh_type")},
                    evidence=[_evidence(backend_id=backend_id, source_path=source_path, method="gmsh-cell-type-summary")],
                ),
            )
            cell_by_asset_dimension.setdefault((asset_id, cell_dimension), entity)
            _contains(relations, backend_id=backend_id, source=root, target=entity, source_path=source_path)
        for entity_index, native in enumerate(file_summary.get("entities") or []):
            if not isinstance(native, dict):
                continue
            native_dimension = _native_dimension(native.get("dimension"))
            if native_dimension is None:
                native_dimension = dimension
            native_tag = native.get("tag", entity_index)
            geometry = _add_entity(
                entities,
                SpatialEntity(
                    entity_id=_stable_id("entity", graph.graph_id, asset_id, "geometry", native_dimension, native_tag),
                    entity_kind=_gmsh_geometry_kind(native),
                    name=str(native.get("name") or native.get("subtype") or f"Gmsh entity {native_tag}"),
                    topological_dimension=native_dimension,
                    embedding_dimension=dimension,
                    coordinate_frame_id=frame_id,
                    native_id=native_tag,
                    source_backend=backend_id,
                    source_asset_id=asset_id,
                    source_path=source_path,
                    bounds=_bounds(native.get("bounds"), frame_id=frame_id, active_dimensions=dimension),
                    evidence_status=SpatialEvidenceStatus.explicit,
                    confidence=1.0,
                    metadata={
                        "gmsh_kind": native.get("kind"),
                        "subtype": native.get("subtype"),
                        "members": list(native.get("members") or [])[:256],
                        "physical_tags": list(native.get("physical_tags") or [])[:256],
                    },
                    evidence=[_evidence(backend_id=backend_id, source_path=source_path, method="gmsh-native-entity")],
                ),
            )
            geometry_by_native[(asset_id, native_dimension, str(native_tag))] = geometry
            _contains(relations, backend_id=backend_id, source=root, target=geometry, source_path=source_path)
        groups_by_key: dict[tuple[int, str], SpatialEntity] = {}
        for group_index, group in enumerate(file_summary.get("physical_groups") or []):
            if not isinstance(group, dict):
                continue
            group_dimension = _native_dimension(group.get("dimension"))
            if group_dimension is None:
                group_dimension = dimension
            group_tag = group.get("tag", group_index)
            group_entity = _add_entity(
                entities,
                SpatialEntity(
                    entity_id=_stable_id("entity", graph.graph_id, asset_id, "physical-group", group_dimension, group_tag),
                    entity_kind=SpatialEntityKind.physical_group,
                    name=str(group.get("name") or f"Physical group {group_tag}"),
                    topological_dimension=group_dimension,
                    embedding_dimension=dimension,
                    coordinate_frame_id=frame_id,
                    native_id=group_tag,
                    source_backend=backend_id,
                    source_asset_id=asset_id,
                    source_path=source_path,
                    evidence_status=SpatialEvidenceStatus.explicit,
                    confidence=1.0,
                    metadata={
                        "element_count": group.get("element_count"),
                        "members": list(group.get("members") or [])[:256],
                    },
                    evidence=[_evidence(backend_id=backend_id, source_path=source_path, method="gmsh-physical-group")],
                ),
            )
            groups_by_key[(group_dimension, str(group_tag))] = group_entity
            _contains(relations, backend_id=backend_id, source=root, target=group_entity, source_path=source_path)
            _contains(relations, backend_id=backend_id, source=group_entity, target=root, source_path=source_path, kind=SpatialRelationKind.belongs_to)
            for member in group.get("members") or []:
                target = geometry_by_native.get((asset_id, group_dimension, str(member)))
                if target is not None:
                    _contains(relations, backend_id=backend_id, source=group_entity, target=target, source_path=source_path, metadata={"native_member_tag": member})
        for native_key, geometry in geometry_by_native.items():
            if native_key[0] != asset_id:
                continue
            native_physical = geometry.metadata.get("physical_tags") or []
            for physical_tag in native_physical:
                group_entity = groups_by_key.get((native_key[1], str(physical_tag)))
                if group_entity is not None:
                    _contains(relations, backend_id=backend_id, source=group_entity, target=geometry, source_path=source_path, metadata={"native_physical_tag": physical_tag})
    for array_id, ref in arrays.items():
        asset_id = str(ref.source_asset_id or "")
        root = root_by_asset.get(asset_id)
        if root is None:
            diagnostics.append(
                SpatialMappingDiagnostic(
                    code="CRX-SPATIAL-MAP-ARRAY-001",
                    message="ArrayRef source asset could not be matched to a Gmsh file summary.",
                    backend_id=backend_id,
                    source_path=ref.source_path,
                    details={"array_id": array_id, "source_asset_id": ref.source_asset_id},
                )
            )
            continue
        native_role = str(ref.metadata.get("role") or "")
        if native_role in {"mesh_points", "geo_points", "node_tags"} and asset_id in node_by_asset:
            owner = node_by_asset[asset_id]
        elif ref.association == "point" and asset_id in node_by_asset:
            owner = node_by_asset[asset_id]
        elif ref.association == "cell" and (asset_id, 3) in cell_by_asset_dimension:
            owner = cell_by_asset_dimension[(asset_id, 3)]
        else:
            owner = root
        _link_array(
            links,
            ref=ref,
            owner_entity_id=owner.entity_id,
            frame_id=frame_by_asset.get(asset_id),
            backend_id=backend_id,
            mapping_reason=f"gmsh:{native_role or ref.association or 'unclassified'}",
        )
        mapped.add(array_id)
    graph.default_coordinate_frame_id = sorted(frames)[0] if len(frames) == 1 else None
    graph.status = SpatialGraphStatus.complete if entities else SpatialGraphStatus.draft
    snapshot = SpatialGraphSnapshot(
        graph=graph,
        coordinate_frames=sorted(frames.values(), key=lambda item: item.frame_id),
        entities=sorted(entities.values(), key=lambda item: item.entity_id),
        relations=sorted(relations.values(), key=lambda item: item.relation_id),
        array_links=sorted(links.values(), key=lambda item: item.link_id),
    )
    return SpatialMappingResult(
        backend_id=backend_id,
        execution_id=result.execution_id,
        graph_id=graph.graph_id,
        snapshot=snapshot,
        mapped_array_ids=sorted(mapped),
        skipped_array_ids=sorted(set(arrays) - mapped),
        diagnostics=diagnostics,
    )


def _map_vtk(
    *,
    graph: SpatialGraph,
    result: InspectionExecutionResult,
    summary: dict[str, Any],
) -> SpatialMappingResult:
    backend_id = result.backend_id
    arrays = {item.array_id: item for item in result.arrays if item.array_id}
    entities: dict[str, SpatialEntity] = {}
    relations: dict[str, SpatialRelation] = {}
    links: dict[str, SpatialArrayLink] = {}
    frames: dict[str, CoordinateFrame] = {}
    root_by_asset: dict[str, SpatialEntity] = {}
    node_by_asset: dict[str, SpatialEntity] = {}
    cell_by_asset_dimension: dict[tuple[str, int], SpatialEntity] = {}
    frame_by_asset: dict[str, str] = {}
    mapped: set[str] = set()
    diagnostics: list[SpatialMappingDiagnostic] = []
    files = summary.get("files") if isinstance(summary.get("files"), list) else []
    for index, file_summary in enumerate(files, start=1):
        if not isinstance(file_summary, dict):
            continue
        source_path = str(file_summary.get("source_path") or f"vtk_source_{index}")
        asset_id = f"asset_vtk_{index}"
        dimension = _dimension(file_summary.get("dimension"), 3)
        frame_id = _stable_id("frame", graph.graph_id, asset_id, source_path)
        frame_by_asset[asset_id] = frame_id
        frame = _vtk_frame(
            frame_id=frame_id,
            file_summary=file_summary,
            backend_id=backend_id,
            asset_id=asset_id,
        )
        frames[frame_id] = frame
        status = str(file_summary.get("status") or "unresolved")
        evidence_status = SpatialEvidenceStatus.explicit if status in {"decoded", "inventoried"} else SpatialEvidenceStatus.unresolved
        root = _add_entity(
            entities,
            SpatialEntity(
                entity_id=_stable_id("entity", graph.graph_id, asset_id, "root"),
                entity_kind=SpatialEntityKind.dataset_block,
                name=source_path,
                embedding_dimension=dimension,
                coordinate_frame_id=frame_id,
                native_id=source_path,
                source_backend=backend_id,
                source_asset_id=asset_id,
                source_path=source_path,
                bounds=_bounds(file_summary.get("bounds"), frame_id=frame_id, active_dimensions=dimension, status=evidence_status),
                evidence_status=evidence_status,
                confidence=1.0 if evidence_status == SpatialEvidenceStatus.explicit else None,
                metadata={
                    "vtk_kind": file_summary.get("kind"),
                    "dataset_type": file_summary.get("dataset_type"),
                    "reader": file_summary.get("reader"),
                    "status": status,
                    "point_count": file_summary.get("point_count"),
                    "cell_count": file_summary.get("cell_count"),
                    "extent": file_summary.get("extent"),
                    "spacing": file_summary.get("spacing"),
                    "coordinate_units": file_summary.get("coordinate_units", "unresolved"),
                },
                evidence=[_evidence(backend_id=backend_id, source_path=source_path, method="vtk-file-summary", status=evidence_status)],
            ),
        )
        root_by_asset[asset_id] = root
        point_count = int(file_summary.get("point_count") or 0)
        if point_count > 0:
            node = _add_entity(
                entities,
                SpatialEntity(
                    entity_id=_stable_id("entity", graph.graph_id, asset_id, "points"),
                    entity_kind=SpatialEntityKind.mesh_node,
                    name=f"{source_path} points",
                    embedding_dimension=dimension,
                    coordinate_frame_id=frame_id,
                    source_backend=backend_id,
                    source_asset_id=asset_id,
                    source_path=source_path,
                    bounds=_bounds(file_summary.get("bounds"), frame_id=frame_id, active_dimensions=dimension, status=evidence_status),
                    evidence_status=evidence_status,
                    confidence=1.0 if evidence_status == SpatialEvidenceStatus.explicit else None,
                    metadata={"aggregate": True, "count": point_count},
                    evidence=[_evidence(backend_id=backend_id, source_path=source_path, method="vtk-point-count", status=evidence_status)],
                ),
            )
            node_by_asset[asset_id] = node
            _contains(relations, backend_id=backend_id, source=root, target=node, source_path=source_path)
        for type_index, cell_type in enumerate(file_summary.get("cell_types") or []):
            if not isinstance(cell_type, dict):
                continue
            cell_dimension = _native_dimension(cell_type.get("dimension"))
            if cell_dimension is None:
                cell_dimension = dimension
            native_type = cell_type.get("vtk_type", type_index)
            entity = _add_entity(
                entities,
                SpatialEntity(
                    entity_id=_stable_id("entity", graph.graph_id, asset_id, "cell-type", native_type, type_index),
                    entity_kind=_entity_kind_for_dimension(cell_dimension, geometry=False),
                    name=str(cell_type.get("name") or f"VTK type {native_type}"),
                    topological_dimension=cell_dimension,
                    embedding_dimension=dimension,
                    coordinate_frame_id=frame_id,
                    native_id=native_type,
                    source_backend=backend_id,
                    source_asset_id=asset_id,
                    source_path=source_path,
                    evidence_status=SpatialEvidenceStatus.explicit,
                    confidence=1.0,
                    metadata={"aggregate": True, "count": int(cell_type.get("count") or 0), "vtk_type": native_type},
                    evidence=[_evidence(backend_id=backend_id, source_path=source_path, method="vtk-cell-type-summary")],
                ),
            )
            cell_by_asset_dimension.setdefault((asset_id, cell_dimension), entity)
            _contains(relations, backend_id=backend_id, source=root, target=entity, source_path=source_path)
        for reference_index, reference in enumerate(file_summary.get("references") or []):
            if not isinstance(reference, dict):
                continue
            reference_path = str(reference.get("file") or reference.get("source") or f"reference_{reference_index}")
            child = _add_entity(
                entities,
                SpatialEntity(
                    entity_id=_stable_id("entity", graph.graph_id, asset_id, "reference", reference_path, reference_index),
                    entity_kind=SpatialEntityKind.dataset_block,
                    name=reference_path,
                    embedding_dimension=dimension,
                    native_id=reference_path,
                    source_backend=backend_id,
                    source_asset_id=asset_id,
                    source_path=source_path,
                    evidence_status=SpatialEvidenceStatus.explicit,
                    confidence=1.0,
                    metadata={
                        "reference_path": reference_path,
                        "time": reference.get("time"),
                        "safe": bool(reference.get("safe")),
                        "selected": bool(reference.get("selected")),
                        "external_reference_loaded": False,
                    },
                    evidence=[_evidence(backend_id=backend_id, source_path=source_path, method="vtk-reference-inventory")],
                ),
            )
            _contains(relations, backend_id=backend_id, source=root, target=child, source_path=source_path)
    for array_id, ref in arrays.items():
        asset_id = str(ref.source_asset_id or "")
        root = root_by_asset.get(asset_id)
        if root is None:
            diagnostics.append(
                SpatialMappingDiagnostic(
                    code="CRX-SPATIAL-MAP-ARRAY-001",
                    message="ArrayRef source asset could not be matched to a VTK file summary.",
                    backend_id=backend_id,
                    source_path=ref.source_path,
                    details={"array_id": array_id, "source_asset_id": ref.source_asset_id},
                )
            )
            continue
        native_role = str(ref.metadata.get("role") or ref.metadata.get("name") or "")
        if (_array_role(ref) == SpatialArrayRole.coordinates or ref.association == "point") and asset_id in node_by_asset:
            owner = node_by_asset[asset_id]
        elif ref.association == "cell":
            candidates = [entity for (candidate_asset, _), entity in cell_by_asset_dimension.items() if candidate_asset == asset_id]
            owner = sorted(candidates, key=lambda item: item.entity_id)[0] if len(candidates) == 1 else root
        else:
            owner = root
        _link_array(
            links,
            ref=ref,
            owner_entity_id=owner.entity_id,
            frame_id=frame_by_asset.get(asset_id),
            backend_id=backend_id,
            mapping_reason=f"vtk:{native_role or ref.association or 'unclassified'}",
        )
        mapped.add(array_id)
    graph.default_coordinate_frame_id = sorted(frames)[0] if len(frames) == 1 else None
    graph.status = SpatialGraphStatus.complete if entities else SpatialGraphStatus.draft
    snapshot = SpatialGraphSnapshot(
        graph=graph,
        coordinate_frames=sorted(frames.values(), key=lambda item: item.frame_id),
        entities=sorted(entities.values(), key=lambda item: item.entity_id),
        relations=sorted(relations.values(), key=lambda item: item.relation_id),
        array_links=sorted(links.values(), key=lambda item: item.link_id),
    )
    return SpatialMappingResult(
        backend_id=backend_id,
        execution_id=result.execution_id,
        graph_id=graph.graph_id,
        snapshot=snapshot,
        mapped_array_ids=sorted(mapped),
        skipped_array_ids=sorted(set(arrays) - mapped),
        diagnostics=diagnostics,
    )


def build_spatial_mapping(
    *,
    case_id: str,
    result: InspectionExecutionResult,
    source_manifest_id: str | None = None,
    graph_id: str | None = None,
) -> SpatialMappingResult:
    """Build a canonical graph snapshot from one supported native execution result."""

    if result.backend_id not in SUPPORTED_MAPPING_BACKENDS:
        raise SpatialMappingError(f"Unsupported spatial mapping backend: {result.backend_id}")
    summary = _backend_summary(result)
    graph = _base_graph(
        case_id=case_id,
        backend_id=result.backend_id,
        execution_id=result.execution_id,
        source_manifest_id=source_manifest_id,
        graph_id=graph_id,
    )
    if result.backend_id == "openfoam.native":
        return _map_openfoam(graph=graph, result=result, summary=summary)
    if result.backend_id == "gmsh.native":
        return _map_gmsh(graph=graph, result=result, summary=summary)
    return _map_vtk(graph=graph, result=result, summary=summary)


def persist_spatial_mapping(
    *,
    case: Any,
    result: InspectionExecutionResult,
    state_root: str | Any,
    source_manifest_id: str | None = None,
    graph_id: str | None = None,
) -> SpatialMappingResult:
    """Build, persist and attach one compact graph reference to a ReflexCase-like object."""

    mapping = build_spatial_mapping(
        case_id=str(case.case_id),
        result=result,
        source_manifest_id=source_manifest_id,
        graph_id=graph_id,
    )
    store = SpatialStore(state_root)
    reference = store.put_snapshot(
        mapping.snapshot,
        replace=True,
        require_registered_arrays=True,
    )
    attach_spatial_graph_ref(case, reference)
    reports = case.metadata.setdefault("spatial_mapping", [])
    if not isinstance(reports, list):
        reports = []
        case.metadata["spatial_mapping"] = reports
    reports[:] = [item for item in reports if item.get("graph_id") != mapping.graph_id]
    reports.append(mapping.compact_report())
    reports.sort(key=lambda item: str(item.get("graph_id", "")))
    return mapping


__all__ = [
    "SPATIAL_MAPPING_VERSION",
    "SUPPORTED_MAPPING_BACKENDS",
    "SpatialMappingDiagnostic",
    "SpatialMappingError",
    "SpatialMappingResult",
    "build_spatial_mapping",
    "persist_spatial_mapping",
]
