import json

from caereflex.physics import (
    PHYSICS_RULE_PROTOCOL_VERSION,
    RuleStatus,
    evaluate_openfoam_cfd,
    openfoam_cfd_engine,
)


def complete_context():
    return {
        "fields": [
            {"name": "U", "class": "volVectorField", "association": "cell", "dimensions": [0, 1, -1, 0, 0, 0, 0], "source_path": "0/U"},
            {"name": "p", "class": "volScalarField", "association": "cell", "dimensions": [0, 2, -2, 0, 0, 0, 0], "source_path": "0/p"},
            {"name": "nu", "class": "volScalarField", "association": "cell", "dimensions": [0, 2, -1, 0, 0, 0, 0], "source_path": "constant/transportProperties"},
        ],
        "mesh": {"face_count": 6, "internal_face_count": 0, "boundary_face_count": 6, "cell_count": 1},
        "patches": [
            {"name": "walls", "start_face": 0, "face_count": 4},
            {"name": "frontAndBack", "start_face": 4, "face_count": 2},
        ],
    }


def test_protocol_and_manifest_are_versioned_and_deterministic():
    engine = openfoam_cfd_engine()
    assert engine.pack.protocol_version == PHYSICS_RULE_PROTOCOL_VERSION
    report_a = engine.evaluate(complete_context(), case_id="case_1", backend_id="openfoam.native")
    report_b = engine.evaluate(complete_context(), case_id="case_1", backend_id="openfoam.native")
    assert report_a.input_digest == report_b.input_digest
    assert report_a.report_digest == report_b.report_digest
    assert [item.rule_id for item in report_a.results] == sorted(item.rule_id for item in report_a.results)
    json.dumps(report_a.model_dump(mode="json"), allow_nan=False)


def test_complete_consistent_case_passes_all_six_rules():
    report = evaluate_openfoam_cfd(complete_context(), case_id="case_1")
    assert report.summary[RuleStatus.consistent.value] == 6
    assert report.summary[RuleStatus.inconsistent.value] == 0
    assert all(item.evidence for item in report.results)
    assert all(item.limitation for item in report.results)


def test_dimension_conflict_is_inconsistent_with_exact_evidence_path():
    context = complete_context()
    context["fields"][0]["dimensions"] = [0, 0, 0, 0, 0, 0, 0]
    report = evaluate_openfoam_cfd(context)
    result = next(item for item in report.results if item.rule_id == "OF-CFD-DIM-U-001")
    assert result.status == RuleStatus.inconsistent.value
    assert result.evidence[0].path == "/fields/0/dimensions"
    assert result.remediation


def test_missing_dimensions_block_without_name_inference():
    context = complete_context()
    context["fields"][1].pop("dimensions")
    result = next(item for item in evaluate_openfoam_cfd(context).results if item.rule_id == "OF-CFD-DIM-P-001")
    assert result.status == RuleStatus.blocked.value
    assert "field:p:dimensions" in result.missing_evidence


def test_patch_overlap_and_topology_mismatch_are_detected():
    context = complete_context()
    context["patches"][1]["start_face"] = 3
    context["mesh"]["boundary_face_count"] = 5
    report = evaluate_openfoam_cfd(context)
    statuses = {item.rule_id: item.status for item in report.results}
    assert statuses["OF-CFD-PATCH-RANGE-001"] == RuleStatus.inconsistent.value
    assert statuses["OF-CFD-TOPO-COUNT-001"] == RuleStatus.inconsistent.value


def test_absent_mesh_is_not_falsely_reported_consistent():
    context = complete_context()
    context["mesh"] = None
    context["patches"] = []
    report = evaluate_openfoam_cfd(context)
    statuses = {item.rule_id: item.status for item in report.results}
    assert statuses["OF-CFD-TOPO-COUNT-001"] == RuleStatus.not_evaluated.value
    assert statuses["OF-CFD-PATCH-RANGE-001"] == RuleStatus.not_evaluated.value


def test_pack_explicitly_excludes_validation_claims():
    exclusions = set(openfoam_cfd_engine().pack.exclusions)
    assert {"convergence", "mesh independence", "turbulence-model suitability", "experimental validation", "certification", "design safety"} <= exclusions
