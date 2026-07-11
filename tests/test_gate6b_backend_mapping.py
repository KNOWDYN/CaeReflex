from __future__ import annotations

from caereflex.contracts import ArrayRef, InspectionExecutionResult
from caereflex.spatial import (
    SpatialArrayRole,
    SpatialEntityKind,
    SpatialEvidenceStatus,
    SpatialMappingError,
    SpatialStore,
    build_spatial_mapping,
)

_DIGEST = "a" * 64


def _array(
    array_id: str,
    *,
    asset: str,
    role: str,
    association: str,
    source_path: str,
    shape: tuple[int, ...] = (1,),
    components: list[str] | None = None,
) -> ArrayRef:
    return ArrayRef(
        uri=f"caereflex-artifact://sha256/{_DIGEST}",
        format="raw",
        shape=shape,
        dtype="float64" if role in {"mesh_points", "field_values", "internal_field"} else "int64",
        checksum=_DIGEST,
        array_id=array_id,
        source_asset_id=asset,
        source_path=source_path,
        association=association,
        component_names=components or [],
        backend="test",
        backend_version="1.0.0",
        metadata={"role": role},
    )


def _result(backend_id: str, summary: dict, arrays: list[ArrayRef]) -> InspectionExecutionResult:
    return InspectionExecutionResult(
        execution_id=f"exec_{backend_id.replace('.', '_')}",
        job_id="job_gate6b",
        plugin_id=backend_id.split(".", 1)[0],
        backend_id=backend_id,
        backend_version="1.0.0",
        status="success",
        started_at="2026-07-11T00:00:00Z",
        completed_at="2026-07-11T00:00:01Z",
        arrays=arrays,
        metadata={"backend_result": {"summary": summary}},
    )


def test_openfoam_maps_patches_cells_and_arrays_without_frame_assumptions() -> None:
    summary = {
        "format": "OpenFOAM",
        "mesh": {
            "points": 8,
            "faces": 6,
            "cells": 1,
            "internal_faces": 0,
            "bounds": [[0.0, 1.0], [0.0, 1.0], [0.0, 1.0]],
            "complete_topology": True,
        },
        "patches": [
            {"name": "walls", "type": "wall", "n_faces": 4, "start_face": 0},
            {"name": "inlet", "type": "patch", "n_faces": 1, "start_face": 4},
        ],
        "time_directories": ["0", "1"],
        "field_count": 1,
    }
    arrays = [
        _array(
            "arr_points",
            asset="asset_openfoam_mesh",
            role="mesh_points",
            association="point",
            source_path="constant/polyMesh/points",
            shape=(8, 3),
            components=["x", "y", "z"],
        ),
        _array(
            "arr_faces",
            asset="asset_openfoam_mesh",
            role="face_connectivity",
            association="topology",
            source_path="constant/polyMesh/faces",
            shape=(24,),
        ),
        _array(
            "arr_p",
            asset="asset_openfoam_case",
            role="internal_field",
            association="cell",
            source_path="0/p",
        ),
    ]
    mapping = build_spatial_mapping(
        case_id="case_openfoam",
        source_manifest_id="manifest_openfoam",
        result=_result("openfoam.native", summary, arrays),
    )
    snapshot = mapping.snapshot
    assert len(snapshot.coordinate_frames) == 1
    assert snapshot.coordinate_frames[0].evidence_status == SpatialEvidenceStatus.unresolved.value
    assert snapshot.coordinate_frames[0].origin is None
    assert snapshot.coordinate_frames[0].basis is None
    kinds = [entity.entity_kind for entity in snapshot.entities]
    assert kinds.count(SpatialEntityKind.patch.value) == 2
    assert SpatialEntityKind.mesh_cell.value in kinds
    assert SpatialEntityKind.mesh_face.value in kinds
    assert SpatialEntityKind.mesh_node.value in kinds
    assert {link.role for link in snapshot.array_links} >= {
        SpatialArrayRole.coordinates.value,
        SpatialArrayRole.connectivity.value,
        SpatialArrayRole.field.value,
    }
    assert mapping.skipped_array_ids == []
    assert all(relation.relation_kind != "maps_to" for relation in snapshot.relations)


def test_gmsh_maps_geometry_physical_groups_and_mesh_as_distinct_entities() -> None:
    summary = {
        "format": "Gmsh",
        "files": [
            {
                "source_path": "model.msh",
                "kind": "mesh",
                "status": "decoded",
                "reader": "gmsh.core-ascii",
                "dimension": 3,
                "node_count": 4,
                "element_count": 1,
                "bounds": [[0.0, 1.0], [0.0, 1.0], [0.0, 1.0]],
                "cell_types": [
                    {"gmsh_type": 4, "name": "tetrahedron", "dimension": 3, "count": 1}
                ],
                "entities": [
                    {"dimension": 3, "tag": 10, "physical_tags": [7], "bounds": [[0.0, 1.0], [0.0, 1.0], [0.0, 1.0]]}
                ],
                "physical_groups": [
                    {"dimension": 3, "tag": 7, "name": "fluid", "element_count": 1}
                ],
                "arrays": {},
            }
        ],
    }
    arrays = [
        _array(
            "arr_gmsh_points",
            asset="asset_gmsh_1",
            role="mesh_points",
            association="point",
            source_path="model.msh",
            shape=(4, 3),
            components=["x", "y", "z"],
        ),
        _array(
            "arr_gmsh_connectivity",
            asset="asset_gmsh_1",
            role="element_connectivity",
            association="cell",
            source_path="model.msh",
            shape=(4,),
        ),
    ]
    mapping = build_spatial_mapping(
        case_id="case_gmsh",
        source_manifest_id="manifest_gmsh",
        result=_result("gmsh.native", summary, arrays),
    )
    kinds = {entity.entity_kind for entity in mapping.snapshot.entities}
    assert SpatialEntityKind.geometry_volume.value in kinds
    assert SpatialEntityKind.mesh_cell.value in kinds
    assert SpatialEntityKind.physical_group.value in kinds
    physical = next(
        entity for entity in mapping.snapshot.entities
        if entity.entity_kind == SpatialEntityKind.physical_group.value
    )
    geometry = next(
        entity for entity in mapping.snapshot.entities
        if entity.entity_kind == SpatialEntityKind.geometry_volume.value
    )
    assert any(
        relation.source_entity_id == physical.entity_id
        and relation.target_entity_id == geometry.entity_id
        and relation.relation_kind == "contains"
        for relation in mapping.snapshot.relations
    )
    assert all(relation.relation_kind != "maps_to" for relation in mapping.snapshot.relations)


def test_gmsh_geo_membership_is_mapped_only_when_explicit() -> None:
    summary = {
        "format": "Gmsh",
        "files": [
            {
                "source_path": "geometry.geo",
                "kind": "geo_declarations",
                "status": "decoded",
                "reader": "gmsh.geo-declaration-parser",
                "dimension": 2,
                "point_count": 4,
                "bounds": [[0.0, 1.0], [0.0, 1.0], [0.0, 0.0]],
                "entities": [
                    {"kind": "surface", "subtype": "surface", "dimension": 2, "tag": 20, "members": [1]}
                ],
                "physical_groups": [
                    {"kind": "surface", "dimension": 2, "tag": 3, "name": "wall", "members": [20]}
                ],
            }
        ],
    }
    mapping = build_spatial_mapping(
        case_id="case_geo",
        result=_result("gmsh.native", summary, []),
    )
    physical = next(entity for entity in mapping.snapshot.entities if entity.entity_kind == "physical_group")
    surface = next(entity for entity in mapping.snapshot.entities if entity.entity_kind == "geometry_surface")
    assert any(
        relation.source_entity_id == physical.entity_id
        and relation.target_entity_id == surface.entity_id
        for relation in mapping.snapshot.relations
    )


def test_vtk_maps_dataset_cells_fields_and_explicit_direction_frame() -> None:
    summary = {
        "format": "VTK",
        "files": [
            {
                "source_path": "result.vtu",
                "kind": "vtk_dataset",
                "status": "decoded",
                "reader": "vtk.core",
                "dataset_type": "UnstructuredGrid",
                "point_count": 4,
                "cell_count": 1,
                "dimension": 3,
                "bounds": [[0.0, 1.0], [0.0, 1.0], [0.0, 1.0]],
                "origin": [1.0, 2.0, 3.0],
                "direction": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
                "cell_types": [
                    {"vtk_type": 10, "name": "tetra", "dimension": 3, "count": 1}
                ],
                "fields": [
                    {"name": "pressure", "association": "cell", "array_id": "arr_vtk_pressure"}
                ],
                "arrays": {},
            }
        ],
    }
    arrays = [
        _array(
            "arr_vtk_points",
            asset="asset_vtk_1",
            role="mesh_points",
            association="point",
            source_path="result.vtu",
            shape=(4, 3),
            components=["x", "y", "z"],
        ),
        _array(
            "arr_vtk_cells",
            asset="asset_vtk_1",
            role="ragged_cell_connectivity",
            association="cell",
            source_path="result.vtu",
            shape=(4,),
        ),
        _array(
            "arr_vtk_pressure",
            asset="asset_vtk_1",
            role="vtk_data_array",
            association="cell",
            source_path="result.vtu",
        ),
    ]
    mapping = build_spatial_mapping(
        case_id="case_vtk",
        source_manifest_id="manifest_vtk",
        result=_result("vtk.native", summary, arrays),
    )
    frame = mapping.snapshot.coordinate_frames[0]
    assert frame.evidence_status == SpatialEvidenceStatus.explicit.value
    assert frame.origin == (1.0, 2.0, 3.0)
    assert frame.handedness == "right"
    assert frame.length_unit is None
    assert frame.length_unit_status == SpatialEvidenceStatus.unresolved.value
    assert any(entity.entity_kind == SpatialEntityKind.mesh_cell.value for entity in mapping.snapshot.entities)
    assert any(link.role == SpatialArrayRole.field.value for link in mapping.snapshot.array_links)


def test_vtk_collection_references_remain_inventory_only() -> None:
    summary = {
        "format": "VTK",
        "files": [
            {
                "source_path": "series.pvd",
                "kind": "vtk_collection",
                "status": "inventoried",
                "references": [
                    {"file": "step0.vtu", "time": 0.0, "safe": True, "selected": True},
                    {"file": "../outside.vtu", "time": 1.0, "safe": False, "selected": False},
                ],
            }
        ],
    }
    mapping = build_spatial_mapping(
        case_id="case_collection",
        result=_result("vtk.native", summary, []),
    )
    children = [entity for entity in mapping.snapshot.entities if entity.metadata.get("reference_path")]
    assert len(children) == 2
    assert all(entity.metadata["external_reference_loaded"] is False for entity in children)


def test_mapping_ids_are_deterministic_and_snapshot_persists(tmp_path) -> None:
    summary = {
        "format": "OpenFOAM",
        "mesh": {"points": 1, "faces": 0, "cells": 0, "bounds": [[0, 0], [0, 0], [0, 0]]},
        "patches": [],
        "time_directories": [],
        "field_count": 0,
    }
    result = _result("openfoam.native", summary, [])
    first = build_spatial_mapping(
        case_id="case_repeatable",
        source_manifest_id="manifest_repeatable",
        result=result,
    )
    second = build_spatial_mapping(
        case_id="case_repeatable",
        source_manifest_id="manifest_repeatable",
        result=result,
    )
    assert first.graph_id == second.graph_id
    assert [entity.entity_id for entity in first.snapshot.entities] == [
        entity.entity_id for entity in second.snapshot.entities
    ]
    store = SpatialStore(tmp_path)
    reference = store.put_snapshot(first.snapshot, require_registered_arrays=False)
    assert reference.graph_id == first.graph_id
    assert store.snapshot(first.graph_id).graph.metadata["cross_format_equivalence_asserted"] is False
    assert store.validate_integrity() == []


def test_unsupported_backend_and_missing_summary_fail_closed() -> None:
    unsupported = _result("core.manifest-audit", {"format": "manifest"}, [])
    try:
        build_spatial_mapping(case_id="case", result=unsupported)
    except SpatialMappingError as exc:
        assert "Unsupported" in str(exc)
    else:
        raise AssertionError("unsupported backend must fail")

    missing = _result("vtk.native", {}, [])
    missing.metadata = {}
    try:
        build_spatial_mapping(case_id="case", result=missing)
    except SpatialMappingError as exc:
        assert "summary" in str(exc)
    else:
        raise AssertionError("missing backend summary must fail")
