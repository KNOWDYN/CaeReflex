from __future__ import annotations

from caereflex.arrays import ArrayService
from caereflex.core.models import (
    BoundaryConditionRecord,
    ReflexCase,
    ResultFieldRecord,
    SolverRecord,
)
from caereflex.rules import evaluate_case_rules, evaluate_rule_pack


def _good_case(state_root):
    arrays = ArrayService(state_root)
    points = arrays.register_numeric(
        [
            0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0,
            0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1,
        ],
        dtype="float64", shape=(8, 3), source_path="constant/polyMesh/points",
        association="point", component_names=["x", "y", "z"], backend="openfoam.native",
        metadata={"role": "mesh_points"},
    )
    offsets = arrays.register_numeric(
        [0, 4, 8, 12, 16, 20, 24], dtype="int64", shape=(7,),
        source_path="constant/polyMesh/faces", association="topology", backend="openfoam.native",
        metadata={"role": "face_offsets"},
    )
    connectivity = arrays.register_numeric(
        [0, 1, 2, 3, 4, 7, 6, 5, 0, 4, 5, 1, 1, 5, 6, 2, 2, 6, 7, 3, 3, 7, 4, 0],
        dtype="int64", shape=(24,), source_path="constant/polyMesh/faces",
        association="topology", backend="openfoam.native", metadata={"role": "face_connectivity"},
    )
    owner = arrays.register_numeric(
        [0, 0, 0, 0, 0, 0], dtype="int64", shape=(6,), source_path="constant/polyMesh/owner",
        association="topology", backend="openfoam.native", metadata={"role": "owner"},
    )
    neighbour = arrays.register_numeric(
        [], dtype="int64", shape=(0,), source_path="constant/polyMesh/neighbour",
        association="topology", backend="openfoam.native", metadata={"role": "neighbour"},
    )
    u = arrays.register_numeric(
        [1.0, 0.0, 0.0], dtype="float64", shape=(1, 3), source_path="0/U",
        association="cell", component_names=["x", "y", "z"], backend="openfoam.native",
        metadata={"role": "internal_field", "field_name": "U"},
    )
    p = arrays.register_numeric(
        [0.0], dtype="float64", shape=(1,), source_path="0/p",
        association="cell", backend="openfoam.native",
        metadata={"role": "internal_field", "field_name": "p"},
    )
    return ReflexCase(
        case_id="case_openfoam_good",
        case_type="openfoam",
        physics_tags=["CFD", "finite volume"],
        inspection_profile="deep",
        solver_records=[SolverRecord(application="icoFoam", start_time="0", end_time="10", metadata={"deltaT": "0.1", "writeInterval": "1"})],
        result_fields=[ResultFieldRecord(name="U"), ResultFieldRecord(name="p")],
        boundary_conditions=[
            BoundaryConditionRecord(patch="walls", type="wall"),
            BoundaryConditionRecord(patch="walls", field="U", type="fixedValue"),
            BoundaryConditionRecord(patch="walls", field="p", type="zeroGradient"),
        ],
        dimensional_checks=[
            {"check_id": "check_u", "status": "consistent", "subject_name": "U", "context": "field", "message": "velocity dimensions", "evidence_paths": ["0/U"]},
            {"check_id": "check_p", "status": "consistent", "subject_name": "p", "context": "field", "message": "kinematic pressure dimensions", "evidence_paths": ["0/p"]},
        ],
        array_references=[item.model_dump(mode="json") for item in (points, offsets, connectivity, owner, neighbour, u, p)],
        metadata={
            "inspection_execution": {"backend_id": "openfoam.native", "status": "success"},
            "native_openfoam": {
                "mesh": {
                    "points": 8, "faces": 6, "cells": 1, "internal_faces": 0,
                    "complete_topology": True,
                    "points_array_id": points.array_id,
                    "face_offsets_array_id": offsets.array_id,
                    "face_connectivity_array_id": connectivity.array_id,
                    "owner_array_id": owner.array_id,
                    "neighbour_array_id": neighbour.array_id,
                },
                "patches": [{"name": "walls", "type": "wall", "n_faces": 6, "start_face": 0, "physical_type": None}],
                "fields": [
                    {"name": "U", "time": "0", "class": "volVectorField", "components": 3, "dimensions": [0, 1, -1, 0, 0, 0, 0], "storage": "uniform", "tuple_count": 1, "array_id": u.array_id},
                    {"name": "p", "time": "0", "class": "volScalarField", "components": 1, "dimensions": [0, 2, -2, 0, 0, 0, 0], "storage": "nonuniform", "tuple_count": 1, "array_id": p.array_id},
                ],
            },
        },
    )


def test_good_openfoam_fixture_is_consistent_and_deterministic(tmp_path):
    case = _good_case(tmp_path)
    first = evaluate_rule_pack(case, pack_id="openfoam.cfd-core", state_root=tmp_path)
    second = evaluate_rule_pack(case, pack_id="openfoam.cfd-core", state_root=tmp_path)
    assert first.status == "consistent"
    assert first.run_id == second.run_id
    assert first.canonical_sha256 == second.canonical_sha256
    assert {item.status for item in first.results} == {"consistent"}
    assert [item.rule_id for item in first.results] == sorted(item.rule_id for item in first.results)


def test_explicit_openfoam_conflicts_are_inconsistent(tmp_path):
    case = _good_case(tmp_path)
    case.metadata["native_openfoam"]["patches"] = [
        {"name": "a", "type": "wall", "n_faces": 4, "start_face": 0},
        {"name": "b", "type": "patch", "n_faces": 4, "start_face": 2},
    ]
    case.dimensional_checks[0]["status"] = "conflicted"
    case.dimensional_checks[0]["blocks_automated_interpretation"] = True
    case.solver_records[0].start_time = "20"
    report = evaluate_rule_pack(case, pack_id="openfoam.cfd-core", state_root=tmp_path)
    assert report.status == "inconsistent"
    statuses = {item.rule_id: item.status for item in report.results}
    assert statuses["OF-CFD-BOUNDARY-001"] == "inconsistent"
    assert statuses["OF-CFD-DIMENSIONS-001"] == "inconsistent"
    assert statuses["OF-CFD-TIME-001"] == "inconsistent"


def test_missing_deep_evidence_is_not_false_consistency(tmp_path):
    case = ReflexCase(case_id="case_shallow", case_type="openfoam", physics_tags=["CFD"], inspection_profile="standard")
    report = evaluate_rule_pack(case, pack_id="openfoam.cfd-core", state_root=tmp_path)
    assert report.status == "incomplete"
    assert any(item.status == "not_evaluated" for item in report.results)
    assert any(item.status == "unknown" for item in report.results)


def test_missing_array_registry_blocks_heavy_evidence_rule(tmp_path):
    good_root = tmp_path / "good"
    missing_root = tmp_path / "missing"
    case = _good_case(good_root)
    report = evaluate_rule_pack(case, pack_id="openfoam.cfd-core", state_root=missing_root)
    assert report.status == "blocked"
    mesh = next(item for item in report.results if item.rule_id == "OF-CFD-MESH-001")
    assert mesh.status == "blocked"


def test_attach_replaces_same_pack_run_and_preserves_limitations(tmp_path):
    case = _good_case(tmp_path)
    first = evaluate_case_rules(case, state_root=tmp_path, attach=True)
    second = evaluate_case_rules(case, state_root=tmp_path, attach=True)
    runs = case.metadata["physics_consistency"]["runs"]
    assert len(runs) == 1
    assert runs[0]["pack_id"] == "openfoam.cfd-core"
    assert first.canonical_sha256 == second.canonical_sha256
    assert any("convergence" in item.lower() for item in case.agent_summary.do_not_claim)
