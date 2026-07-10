import json
from pathlib import Path
import shutil

from typer.testing import CliRunner

from caereflex.arrays import ArrayService
from caereflex.cli.main import app
from caereflex.contracts import InspectionProfile
from caereflex.core.config import CaeReflexConfig
from caereflex.plugins import get_adapter_plugin
from caereflex.services import doctor_report, inspect_path, scan_path

FIXTURE = Path("examples/openfoam_cavity_native")
runner = CliRunner()


def test_openfoam_plugin_selects_native_backend_for_complete_polymesh():
    manifest, _ = scan_path(FIXTURE, profile=InspectionProfile.deep)
    plugin = get_adapter_plugin("openfoam")
    assert plugin is not None
    plan = plugin.plan(manifest, InspectionProfile.deep, manifest_budget())

    assert plan.metadata["native_requirements_met"] is True
    assert plan.backend_candidates[:2] == ["openfoam.native", "core.manifest-audit"]
    assert "constant/polyMesh/points" in plan.selected_paths


def manifest_budget():
    from caereflex.contracts import InspectionBudget

    return InspectionBudget(max_files=500, max_depth=3, max_bytes_read=25 * 1024 * 1024)


def test_deep_inspection_decodes_mesh_fields_times_and_units(tmp_path: Path):
    state_root = tmp_path / "state"
    case = inspect_path(
        FIXTURE,
        adapter="openfoam",
        profile=InspectionProfile.deep,
        config=CaeReflexConfig(state_dir=state_root),
    )

    execution = case.metadata["inspection_execution"]
    native = case.metadata["openfoam_native"]
    mesh = native["mesh"]

    assert execution["backend_id"] == "openfoam.native"
    assert execution["backend_version"] == "1.0.0"
    assert execution["status"] == "success"
    assert execution["source_mutation_detected"] is False
    assert mesh["native_decoded"] is True
    assert mesh["point_count"] == 8
    assert mesh["face_count"] == 6
    assert mesh["internal_face_count"] == 0
    assert mesh["boundary_face_count"] == 6
    assert mesh["cell_count"] == 1
    assert mesh["patch_count"] == 3
    assert mesh["bounds"] == {"minimum": [0.0, 0.0, 0.0], "maximum": [1.0, 1.0, 1.0]}
    assert [item["name"] for item in mesh["patches"]] == ["movingWall", "fixedWalls", "frontAndBack"]

    assert native["times"] == ["0", "1"]
    assert native["field_availability"] == {"0": ["U", "p"], "1": ["U", "p"]}
    assert {(item["name"], item["time"]) for item in native["fields"]} == {
        ("U", "0"), ("p", "0"), ("U", "1"), ("p", "1")
    }
    assert any(item["name"] == "nu" and item["quantity_kind"] == "kinematic_viscosity" for item in native["materials"])

    quantity_subjects = {
        (item.get("metadata", {}).get("subject_name"), item.get("source_path"))
        for item in case.quantity_evidence
    }
    assert ("U", "0/U") in quantity_subjects
    assert ("p", "0/p") in quantity_subjects
    assert ("nu", "constant/transportProperties") in quantity_subjects

    time_one_fields = {
        (item.name, str(item.metadata.get("time"))): item
        for item in case.result_fields
        if item.metadata.get("time") == "1"
    }
    assert ("U", "1") in time_one_fields
    assert ("p", "1") in time_one_fields

    arrays = ArrayService(state_root)
    point_id = mesh["array_ids"]["points"]
    assert arrays.describe(point_id)["shape"] == [8, 3]
    assert arrays.slice(point_id, 0, 6)["values"] == [0.0, 0.0, 0.0, 1.0, 0.0, 0.0]

    u1 = next(item for item in native["fields"] if item["name"] == "U" and item["time"] == "1")
    p1 = next(item for item in native["fields"] if item["name"] == "p" and item["time"] == "1")
    assert arrays.slice(u1["array_id"], 0, 3)["values"] == [0.5, 0.0, 0.0]
    assert arrays.reduce(p1["array_id"], "mean")["value"] == 0.25


def test_incomplete_legacy_fixture_keeps_manifest_audit_fallback(tmp_path: Path):
    case = inspect_path(
        "examples/openfoam_cavity_minimal",
        adapter="openfoam",
        profile=InspectionProfile.deep,
        config=CaeReflexConfig(state_dir=tmp_path / "state"),
    )
    assert case.metadata["inspection_execution"]["backend_id"] == "core.manifest-audit"
    assert "openfoam_native" not in case.metadata


def test_unsafe_openfoam_construct_yields_partial_literal_only_evidence(tmp_path: Path):
    case_root = tmp_path / "unsafe_case"
    shutil.copytree(FIXTURE, case_root)
    field_path = case_root / "0" / "U"
    original = field_path.read_text(encoding="utf-8")
    field_path.write_text(original + '\n#include "generatedBoundaryValues"\n', encoding="utf-8")
    state_root = tmp_path / "state"

    case = inspect_path(
        case_root,
        adapter="openfoam",
        profile=InspectionProfile.deep,
        config=CaeReflexConfig(state_dir=state_root),
    )

    assert case.metadata["inspection_execution"]["status"] == "partial_success"
    assert any(item.get("code") == "CRX-OF-NATIVE-UNSAFE-001" for item in case.diagnostics)
    assert case.metadata["openfoam_native"]["unsafe_constructs"][0]["code"] == "include"
    assert field_path.read_text(encoding="utf-8") == original + '\n#include "generatedBoundaryValues"\n'


def test_doctor_and_cli_expose_openfoam_native_backend(tmp_path: Path):
    report = doctor_report()
    assert any(item["backend_id"] == "openfoam.native" for item in report["execution_runtime"]["backends"])
    openfoam = next(item for item in report["adapters"] if item["plugin_id"] == "openfoam")
    assert openfoam["plugin_version"] == "1.2.0"
    assert openfoam["time_series_support"] is True

    output = tmp_path / "case.json"
    state_root = tmp_path / "state"
    result = runner.invoke(
        app,
        [
            "inspect",
            str(FIXTURE),
            "--adapter", "openfoam",
            "--profile", "deep",
            "--out", str(output),
            "--json",
        ],
        env={"CAEREFLEX_STATE_DIR": str(state_root)},
    )
    assert result.exit_code == 0
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["metadata"]["inspection_execution"]["backend_id"] == "openfoam.native"
    assert stored["metadata"]["openfoam_native"]["mesh"]["cell_count"] == 1
