"""Gate 6B mapping from frozen Gate 5 backend evidence to spatial graphs.

The mapper is deliberately conservative: it translates explicit backend evidence and
ArrayRef handles into canonical entities and relations, but it never asserts
cross-format equivalence, units, adjacency, coordinate transforms, or mesh quality.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

from caereflex.contracts import ArrayRef, InspectionExecutionResult
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


class SpatialMappingError(ValueError):
    """Raised when frozen backend evidence cannot be mapped safely."""


@dataclass(frozen=True)
class MappingPolicy:
    allow_partial: bool = True
    include_fields: bool = True
    max_entities: int = 100_000
    max_relations: int = 250_000


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:20]}"


def _evidence(backend: str, source_path: str | None, method: str) -> list[SpatialEvidenceRecord]:
    return [SpatialEvidenceRecord(
        evidence_id=_stable_id("ev", backend, source_path, method),
        status=SpatialEvidenceStatus.explicit,
        source_path=source_path,
        parser=backend,
        method=method,
        confidence=1.0,
    )]


def _array_map(result: InspectionExecutionResult) -> dict[str, ArrayRef]:
    return {item.array_id: item for item in result.arrays if item.array_id}


def _bounds(raw: Any, frame_id: str, dimension: int) -> AxisAlignedBounds | None:
    if not isinstance(raw, list) or len(raw) != 3:
        return None
    try:
        minimum = tuple(float(raw[i][0]) for i in range(3))
        maximum = tuple(float(raw[i][1]) for i in range(3))
    except (TypeError, ValueError, IndexError):
        return None
    return AxisAlignedBounds(
        coordinate_frame_id=frame_id,
        minimum=minimum,
        maximum=maximum,
        active_dimensions=max(1, min(3, dimension)),
        evidence_status=SpatialEvidenceStatus.explicit,
        confidence=1.0,
    )


def _frame(frame_id: str, backend: str, asset_id: str | None, dimension: int = 3) -> CoordinateFrame:
    # Backend readers expose coordinates but do not establish origin, basis, units or
    # handedness. Preserve that uncertainty rather than manufacturing a global frame.
    return CoordinateFrame(
        frame_id=frame_id,
        name=f"{backend} source frame",
        dimension=max(1, min(3, dimension or 3)),
        origin=None,
        basis=None,
        handedness=CoordinateHandedness.unknown,
        length_unit=None,
        length_unit_status=SpatialEvidenceStatus.unresolved,
        evidence_status=SpatialEvidenceStatus.unresolved,
        confidence=None,
        source_backend=backend,
        source_asset_id=asset_id,
        metadata={"mapping_stage": "gate6b", "coordinate_semantics": "unresolved"},
    )


def _link_for_ref(
    ref: ArrayRef,
    *,
    owner_entity_id: str,
    role: SpatialArrayRole,
    frame_id: str | None,
) -> SpatialArrayLink:
    return SpatialArrayLink.from_array_ref(
        ref,
        link_id=_stable_id("link", owner_entity_id, ref.array_id, role.value),
        role=role,
        owner_entity_id=owner_entity_id,
        coordinate_frame_id=frame_id,
        evidence_status=SpatialEvidenceStatus.explicit,
        metadata={"source_backend": ref.backend, "source_path": ref.source_path},
    )


def _role(ref: ArrayRef) -> SpatialArrayRole:
    role = str(ref.metadata.get("role", "")).lower()
    if any(token in role for token in ("point", "coordinate", "node_coordinates")):
        return SpatialArrayRole.coordinates
    if "offset" in role:
        return SpatialArrayRole.offsets
    if "cell_type" in role or "element_type" in role:
        return SpatialArrayRole.cell_types
    if any(token in role for token in ("connectivity", "owner", "neighbour")):
        return SpatialArrayRole.connectivity
    if any(token in role for token in ("physical", "membership", "entity_tag")):
        return SpatialArrayRole.membership
    if "normal" in role:
        return SpatialArrayRole.normals
    if ref.association in {"point", "cell", "field", "boundary"} and "field" in role:
        return SpatialArrayRole.field
    return SpatialArrayRole.other


def _base_graph(result: InspectionExecutionResult, case_id: str, source_manifest_id: str | None) -> SpatialGraph:
    return SpatialGraph(
        graph_id=_stable_id("graph", case_id, result.execution_id, result.backend_id),
        case_id=case_id,
        name=f"{result.backend_id} spatial evidence",
        source_manifest_id=source_manifest_id,
        status=SpatialGraphStatus.draft,
        metadata={
            "mapping_stage": "gate6b",
            "execution_id": result.execution_id,
            "backend_id": result.backend_id,
            "backend_version": result.backend_version,
            "cross_format_equivalence_asserted": False,
        },
    )


def map_openfoam(result: InspectionExecutionResult, *, case_id: str, source_manifest_id: str | None = None) -> SpatialGraphSnapshot:
    summary = dict(result.metadata.get("backend_result", {})).get("summary") or result.metadata.get("summary") or {}
    if not summary and isinstance(result.metadata.get("result"), dict):
        summary = result.metadata["result"].get("summary", {})
    mesh = summary.get("mesh", {})
    graph = _base_graph(result, case_id, source_manifest_id)
    frame_id = "openfoam_case_frame"
    frame = _frame(frame_id, result.backend_id, "asset_openfoam_mesh", 3)
    graph.default_coordinate_frame_id = frame_id
    arrays = _array_map(result)

    mesh_id = _stable_id("ent", graph.graph_id, "openfoam_mesh")
    mesh_entity = SpatialEntity(
        entity_id=mesh_id, entity_kind=SpatialEntityKind.region, name="OpenFOAM mesh",
        topological_dimension=3, embedding_dimension=3, coordinate_frame_id=frame_id,
        native_id="polyMesh", source_backend=result.backend_id, source_asset_id="asset_openfoam_mesh",
        source_path="constant/polyMesh", bounds=_bounds(mesh.get("bounds"), frame_id, 3),
        evidence_status=SpatialEvidenceStatus.explicit,
        evidence=_evidence(result.backend_id, "constant/polyMesh", "native OpenFOAM mapping"),
        metadata={
            "point_count": mesh.get("points"), "face_count": mesh.get("faces"),
            "cell_count": mesh.get("cells"), "internal_face_count": mesh.get("internal_faces"),
            "complete_topology": bool(mesh.get("complete_topology", False)),
        },
    )
    entities = [mesh_entity]
    relations: list[SpatialRelation] = []
    links: list[SpatialArrayLink] = []

    for key, role in (
        ("points_array_id", SpatialArrayRole.coordinates),
        ("face_offsets_array_id", SpatialArrayRole.offsets),
        ("face_connectivity_array_id", SpatialArrayRole.connectivity),
        ("owner_array_id", SpatialArrayRole.connectivity),
        ("neighbour_array_id", SpatialArrayRole.connectivity),
    ):
        array_id = mesh.get(key)
        if array_id in arrays:
            links.append(_link_for_ref(arrays[array_id], owner_entity_id=mesh_id, role=role, frame_id=frame_id))

    for patch in summary.get("patches", []):
        patch_id = _stable_id("ent", graph.graph_id, "patch", patch.get("name"), patch.get("start_face"))
        entities.append(SpatialEntity(
            entity_id=patch_id, entity_kind=SpatialEntityKind.patch, name=patch.get("name"),
            topological_dimension=2, embedding_dimension=3, coordinate_frame_id=frame_id,
            native_id=patch.get("name"), source_backend=result.backend_id,
            source_path="constant/polyMesh/boundary", evidence_status=SpatialEvidenceStatus.explicit,
            evidence=_evidence(result.backend_id, "constant/polyMesh/boundary", "boundary patch declaration"),
            metadata={"patch_type": patch.get("type"), "physical_type": patch.get("physical_type"),
                      "face_count": patch.get("n_faces"), "start_face": patch.get("start_face")},
        ))
        relations.append(SpatialRelation(
            relation_id=_stable_id("rel", graph.graph_id, mesh_id, patch_id, "contains"),
            relation_kind=SpatialRelationKind.contains, source_entity_id=mesh_id, target_entity_id=patch_id,
            evidence_status=SpatialEvidenceStatus.explicit,
            evidence=_evidence(result.backend_id, "constant/polyMesh/boundary", "patch membership"),
        ))

    if summary.get("fields"):
        field_region_id = _stable_id("ent", graph.graph_id, "field_region")
        entities.append(SpatialEntity(
            entity_id=field_region_id, entity_kind=SpatialEntityKind.dataset_block, name="OpenFOAM fields",
            topological_dimension=3, embedding_dimension=3, coordinate_frame_id=frame_id,
            source_backend=result.backend_id, evidence_status=SpatialEvidenceStatus.explicit,
            metadata={"time_directories": summary.get("time_directories", [])},
        ))
        relations.append(SpatialRelation(
            relation_id=_stable_id("rel", graph.graph_id, mesh_id, field_region_id, "carries_field"),
            relation_kind=SpatialRelationKind.carries_field, source_entity_id=mesh_id, target_entity_id=field_region_id,
            evidence_status=SpatialEvidenceStatus.explicit,
        ))
        for field in summary.get("fields", []):
            array_id = field.get("array_id")
            if array_id in arrays:
                links.append(_link_for_ref(arrays[array_id], owner_entity_id=field_region_id,
                                           role=SpatialArrayRole.field, frame_id=frame_id))
    graph.status = SpatialGraphStatus.complete if mesh.get("complete_topology") else SpatialGraphStatus.draft
    return SpatialGraphSnapshot(graph=graph, coordinate_frames=[frame], entities=entities, relations=relations, array_links=links)


def _gmsh_kind(kind: str, dimension: int | None) -> SpatialEntityKind:
    normalized = str(kind).lower()
    if normalized in {"point", "geometry_point"} or dimension == 0:
        return SpatialEntityKind.geometry_point
    if normalized in {"curve", "line", "curve_loop"} or dimension == 1:
        return SpatialEntityKind.geometry_curve
    if normalized in {"surface", "surface_loop"} or dimension == 2:
        return SpatialEntityKind.geometry_surface
    if normalized == "volume" or dimension == 3:
        return SpatialEntityKind.geometry_volume
    return SpatialEntityKind.region


def map_gmsh(result: InspectionExecutionResult, *, case_id: str, source_manifest_id: str | None = None) -> SpatialGraphSnapshot:
    summary = dict(result.metadata.get("backend_result", {})).get("summary") or result.metadata.get("summary") or {}
    graph = _base_graph(result, case_id, source_manifest_id)
    arrays = _array_map(result)
    frames: list[CoordinateFrame] = []
    entities: list[SpatialEntity] = []
    relations: list[SpatialRelation] = []
    links: list[SpatialArrayLink] = []

    for index, file_summary in enumerate(summary.get("files", []), start=1):
        if file_summary.get("kind") in {"cad_fingerprint", "file_fingerprint"}:
            continue
        dimension = int(file_summary.get("dimension") or 3)
        frame_id = _stable_id("frame", graph.graph_id, file_summary.get("source_path"), index)
        frames.append(_frame(frame_id, result.backend_id, f"asset_gmsh_{index}", dimension))
        if graph.default_coordinate_frame_id is None:
            graph.default_coordinate_frame_id = frame_id
        block_id = _stable_id("ent", graph.graph_id, "gmsh_file", file_summary.get("source_path"))
        entities.append(SpatialEntity(
            entity_id=block_id, entity_kind=SpatialEntityKind.dataset_block,
            name=file_summary.get("source_path") or f"Gmsh source {index}",
            topological_dimension=dimension, embedding_dimension=max(1, dimension), coordinate_frame_id=frame_id,
            source_backend=result.backend_id, source_path=file_summary.get("source_path"),
            bounds=_bounds(file_summary.get("bounds"), frame_id, dimension),
            evidence_status=SpatialEvidenceStatus.explicit,
            evidence=_evidence(result.backend_id, file_summary.get("source_path"), "native Gmsh mapping"),
            metadata={"reader": file_summary.get("reader"), "status": file_summary.get("status"),
                      "node_count": file_summary.get("node_count") or file_summary.get("point_count"),
                      "element_count": file_summary.get("element_count")},
        ))
        for native in file_summary.get("entities", []):
            native_dimension = native.get("dimension")
            entity_id = _stable_id("ent", graph.graph_id, file_summary.get("source_path"), native.get("kind"), native.get("tag"))
            entities.append(SpatialEntity(
                entity_id=entity_id, entity_kind=_gmsh_kind(native.get("kind", ""), native_dimension),
                name=native.get("name"), topological_dimension=native_dimension,
                embedding_dimension=max(dimension, native_dimension or 0), coordinate_frame_id=frame_id,
                native_id=native.get("tag"), source_backend=result.backend_id,
                source_path=file_summary.get("source_path"), evidence_status=SpatialEvidenceStatus.explicit,
                evidence=_evidence(result.backend_id, file_summary.get("source_path"), "Gmsh entity declaration"),
                metadata={k: v for k, v in native.items() if k not in {"members", "bounds"}},
            ))
            relations.append(SpatialRelation(
                relation_id=_stable_id("rel", graph.graph_id, block_id, entity_id, "contains"),
                relation_kind=SpatialRelationKind.contains, source_entity_id=block_id, target_entity_id=entity_id,
                evidence_status=SpatialEvidenceStatus.explicit,
            ))
        for group in file_summary.get("physical_groups", []):
            group_id = _stable_id("ent", graph.graph_id, file_summary.get("source_path"), "physical", group.get("tag"), group.get("name"))
            entities.append(SpatialEntity(
                entity_id=group_id, entity_kind=SpatialEntityKind.physical_group,
                name=group.get("name"), topological_dimension=group.get("dimension"), embedding_dimension=dimension,
                coordinate_frame_id=frame_id, native_id=group.get("tag"), source_backend=result.backend_id,
                source_path=file_summary.get("source_path"), evidence_status=SpatialEvidenceStatus.explicit,
                metadata={"member_native_ids": group.get("members", []), "kind": group.get("kind")},
            ))
            relations.append(SpatialRelation(
                relation_id=_stable_id("rel", graph.graph_id, block_id, group_id, "contains"),
                relation_kind=SpatialRelationKind.contains, source_entity_id=block_id, target_entity_id=group_id,
                evidence_status=SpatialEvidenceStatus.explicit,
            ))
        for array_id in (file_summary.get("arrays") or {}).values():
            if isinstance(array_id, list):
                continue
            if array_id in arrays:
                links.append(_link_for_ref(arrays[array_id], owner_entity_id=block_id,
                                           role=_role(arrays[array_id]), frame_id=frame_id))
    graph.status = SpatialGraphStatus.complete if entities else SpatialGraphStatus.draft
    return SpatialGraphSnapshot(graph=graph, coordinate_frames=frames, entities=entities, relations=relations, array_links=links)


def map_vtk(result: InspectionExecutionResult, *, case_id: str, source_manifest_id: str | None = None) -> SpatialGraphSnapshot:
    summary = dict(result.metadata.get("backend_result", {})).get("summary") or result.metadata.get("summary") or {}
    graph = _base_graph(result, case_id, source_manifest_id)
    arrays = _array_map(result)
    frames: list[CoordinateFrame] = []
    entities: list[SpatialEntity] = []
    relations: list[SpatialRelation] = []
    links: list[SpatialArrayLink] = []
    for index, dataset in enumerate(summary.get("files", []), start=1):
        if dataset.get("kind") in {"fingerprint", "collection", "parallel_inventory"} and not dataset.get("decoded"):
            continue
        dimension = int(dataset.get("dimension") or 3)
        frame_id = _stable_id("frame", graph.graph_id, dataset.get("source_path"), index)
        frames.append(_frame(frame_id, result.backend_id, f"asset_vtk_{index}", dimension))
        if graph.default_coordinate_frame_id is None:
            graph.default_coordinate_frame_id = frame_id
        entity_id = _stable_id("ent", graph.graph_id, "vtk_dataset", dataset.get("source_path"), index)
        entities.append(SpatialEntity(
            entity_id=entity_id, entity_kind=SpatialEntityKind.dataset_block,
            name=dataset.get("source_path") or dataset.get("dataset_type") or f"VTK dataset {index}",
            topological_dimension=dimension, embedding_dimension=max(1, dimension), coordinate_frame_id=frame_id,
            source_backend=result.backend_id, source_path=dataset.get("source_path"),
            bounds=_bounds(dataset.get("bounds"), frame_id, dimension),
            evidence_status=SpatialEvidenceStatus.explicit,
            evidence=_evidence(result.backend_id, dataset.get("source_path"), "native VTK dataset mapping"),
            metadata={"dataset_type": dataset.get("dataset_type"), "reader": dataset.get("reader"),
                      "point_count": dataset.get("point_count"), "cell_count": dataset.get("cell_count"),
                      "encoding": dataset.get("encoding")},
        ))
        array_ids: list[str] = []
        for value in (dataset.get("arrays") or {}).values():
            if isinstance(value, str):
                array_ids.append(value)
            elif isinstance(value, list):
                array_ids.extend(item for item in value if isinstance(item, str))
        for field in dataset.get("fields", []):
            if isinstance(field, dict) and isinstance(field.get("array_id"), str):
                array_ids.append(field["array_id"])
        for array_id in dict.fromkeys(array_ids):
            if array_id in arrays:
                links.append(_link_for_ref(arrays[array_id], owner_entity_id=entity_id,
                                           role=_role(arrays[array_id]), frame_id=frame_id))
    graph.status = SpatialGraphStatus.complete if entities else SpatialGraphStatus.draft
    return SpatialGraphSnapshot(graph=graph, coordinate_frames=frames, entities=entities, relations=relations, array_links=links)


def map_execution_result(
    result: InspectionExecutionResult | dict[str, Any],
    *,
    case_id: str,
    source_manifest_id: str | None = None,
    policy: MappingPolicy | None = None,
) -> SpatialGraphSnapshot:
    """Map one frozen Gate 5 execution result into a canonical Gate 6 snapshot."""
    parsed = result if isinstance(result, InspectionExecutionResult) else InspectionExecutionResult.model_validate(result)
    policy = policy or MappingPolicy()
    if parsed.backend_id == "openfoam.native":
        snapshot = map_openfoam(parsed, case_id=case_id, source_manifest_id=source_manifest_id)
    elif parsed.backend_id == "gmsh.native":
        snapshot = map_gmsh(parsed, case_id=case_id, source_manifest_id=source_manifest_id)
    elif parsed.backend_id == "vtk.native":
        snapshot = map_vtk(parsed, case_id=case_id, source_manifest_id=source_manifest_id)
    else:
        raise SpatialMappingError(f"Backend {parsed.backend_id!r} has no Gate 6B mapper")
    if len(snapshot.entities) > policy.max_entities:
        raise SpatialMappingError("mapped entity count exceeds policy.max_entities")
    if len(snapshot.relations) > policy.max_relations:
        raise SpatialMappingError("mapped relation count exceeds policy.max_relations")
    return snapshot
