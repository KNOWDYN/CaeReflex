from __future__ import annotations

from caereflex.contracts import ArrayRef, ExecutionStatus, InspectionExecutionResult
from caereflex.spatial import SpatialEntityKind, SpatialRelationKind
from caereflex.spatial.mapping import map_execution_result


def _result(backend_id: str, summary: dict, arrays: list[ArrayRef] | None = None) -> InspectionExecutionResult:
    return InspectionExecutionResult(
        execution_id=f"exec-{backend_id}",
        job_id=f"job-{backend_id}",
        plugin_id=backend_id.split(".")[0],
        backend_id=backend_id,
        backend_version="1.0.0",
        status=ExecutionStatus.success,
        started_at="2026-07-11T00:00:00Z",
        completed_at="2026-07-11T00:00:01Z",
        arrays=arrays or [],
        metadata={"backend_result": {"summary": summary}},
    )


def _array(array_id: str, *, role: str, association: str = "topology", frame: str | None = None) -> ArrayRef:
    return ArrayRef(
        uri=f"caereflex-artifact://sha256/{'a' * 64}",
        format="raw",
        shape=(4,),
        dtype="int64" if association == "topology" else "float64",
        checksum="a" * 64,
        array_id=array_id,
        source_asset_id="asset",
        source_path="source.dat",
        association=association,
        coordinate_frame_ref=frame,
        backend="fixture",
        metadata={"role": role},
    )


def test_openfoam_mapping_preserves_patch_and_lazy_arrays() -> None:
    arrays = [
        _array("points", role="mesh_points", association="point", frame="openfoam_case_frame"),
        _array("faces", role="face_connectivity"),
        _array("field", role="internal_field", association="cell"),
    ]
    result = _result("openfoam.native", {
        "mesh": {
            "points": 8, "faces": 6, "cells": 1, "internal_faces": 0,
            "complete_topology": True,
            "bounds": [[0, 1], [0, 1], [0, 1]],
            "points_array_id": "points", "face_connectivity_array_id": "faces",
        },
        "patches": [{"name": "walls", "type": "wall", "n_faces": 6, "start_face": 0}],
        "fields": [{"name": "U", "time": "0", "array_id": "field"}],
        "time_directories": ["0"],
    }, arrays)
    snapshot = map_execution_result(result, case_id="case-openfoam")
    assert snapshot.graph.status == "complete"
    assert any(item.entity_kind == SpatialEntityKind.patch for item in snapshot.entities)
    assert any(item.relation_kind == SpatialRelationKind.contains for item in snapshot.relations)
    assert {item.array_id for item in snapshot.array_links} == {"points", "faces", "field"}
    assert snapshot.coordinate_frames[0].evidence_status == "unresolved"
    assert snapshot.coordinate_frames[0].length_unit is None


def test_gmsh_mapping_separates_geometry_and_physical_groups() -> None:
    arrays = [_array("coords", role="node_coordinates", association="point")]
    result = _result("gmsh.native", {
        "files": [{
            "source_path": "model.geo", "kind": "geo_declarations", "status": "decoded",
            "reader": "gmsh.geo-declaration-parser", "dimension": 2,
            "point_count": 4, "bounds": [[0, 1], [0, 1], [0, 0]],
            "entities": [{"kind": "curve", "dimension": 1, "tag": 10},
                         {"kind": "surface", "dimension": 2, "tag": 20}],
            "physical_groups": [{"kind": "surface", "dimension": 2, "name": "fluid", "tag": 5, "members": [20]}],
            "arrays": {"points_array_id": "coords"},
        }]
    }, arrays)
    snapshot = map_execution_result(result, case_id="case-gmsh")
    kinds = {item.entity_kind for item in snapshot.entities}
    assert SpatialEntityKind.geometry_curve in kinds
    assert SpatialEntityKind.geometry_surface in kinds
    assert SpatialEntityKind.physical_group in kinds
    assert snapshot.graph.metadata["cross_format_equivalence_asserted"] is False
    assert len(snapshot.array_links) == 1


def test_vtk_mapping_creates_dataset_blocks_without_region_equivalence() -> None:
    arrays = [
        _array("coords", role="dataset_points", association="point"),
        _array("types", role="cell_types"),
    ]
    result = _result("vtk.native", {
        "files": [{
            "source_path": "result.vtu", "kind": "dataset", "decoded": True,
            "dataset_type": "UnstructuredGrid", "reader": "vtk.core", "dimension": 3,
            "point_count": 8, "cell_count": 1, "bounds": [[0, 1], [0, 1], [0, 1]],
            "arrays": {"points_array_id": "coords", "cell_types_array_id": "types"},
        }]
    }, arrays)
    snapshot = map_execution_result(result, case_id="case-vtk")
    assert len(snapshot.entities) == 1
    assert snapshot.entities[0].entity_kind == SpatialEntityKind.dataset_block
    assert len(snapshot.array_links) == 2
    assert not any(item.relation_kind == SpatialRelationKind.maps_to for item in snapshot.relations)


def test_mapping_is_deterministic() -> None:
    result = _result("vtk.native", {"files": [{"source_path": "a.vtk", "kind": "dataset", "decoded": True,
                                                "dataset_type": "POLYDATA", "dimension": 3, "arrays": {}}]})
    first = map_execution_result(result, case_id="case").model_dump_json()
    second = map_execution_result(result, case_id="case").model_dump_json()
    assert first == second
