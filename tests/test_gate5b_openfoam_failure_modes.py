import gzip
from pathlib import Path
import shutil

from caereflex.contracts import InspectionProfile
from caereflex.core.config import CaeReflexConfig
from caereflex.services import inspect_path

FIXTURE = Path("examples/openfoam_cavity_native")


def _inspect(case_root: Path, state_root: Path):
    return inspect_path(
        case_root,
        adapter="openfoam",
        profile=InspectionProfile.deep,
        config=CaeReflexConfig(state_dir=state_root),
    )


def test_binary_mesh_payload_returns_partial_structured_fallback(tmp_path: Path):
    case_root = tmp_path / "binary_case"
    shutil.copytree(FIXTURE, case_root)
    points = case_root / "constant" / "polyMesh" / "points"
    payload = points.read_bytes().replace(b"format ascii;", b"format binary;") + b"\x00\x01"
    points.write_bytes(payload)

    case = _inspect(case_root, tmp_path / "state")

    execution = case.metadata["inspection_execution"]
    native = case.metadata["openfoam_native"]
    assert execution["backend_id"] == "openfoam.native"
    assert execution["status"] == "partial_success"
    assert native["mesh"]["native_decoded"] is False
    assert native["mesh"]["patch_count"] == 3
    assert any(item.get("code") == "CRX-OF-NATIVE-BINARY-001" for item in case.diagnostics)
    assert any(
        attempt["stage"] == "openfoam_native_mesh" and attempt["outcome"] == "failed"
        for attempt in execution["attempts"]
    )
    assert any(
        attempt["stage"] == "openfoam_structured_inventory" and attempt["outcome"] == "success"
        for attempt in execution["attempts"]
    )


def test_malformed_topology_cannot_crash_parent_process(tmp_path: Path):
    case_root = tmp_path / "malformed_case"
    shutil.copytree(FIXTURE, case_root)
    faces = case_root / "constant" / "polyMesh" / "faces"
    faces.write_text(
        faces.read_text(encoding="utf-8").replace("4(4 5 6 7)", "4(4 5 6 99)"),
        encoding="utf-8",
    )

    case = _inspect(case_root, tmp_path / "state")

    execution = case.metadata["inspection_execution"]
    assert execution["status"] == "partial_success"
    assert execution["source_mutation_detected"] is False
    assert case.metadata["openfoam_native"]["mesh"]["native_decoded"] is False
    assert any(item.get("code") == "CRX-OF-NATIVE-MESH-001" for item in case.diagnostics)


def test_gzip_mesh_member_satisfies_native_reader_requirement(tmp_path: Path):
    case_root = tmp_path / "gzip_case"
    shutil.copytree(FIXTURE, case_root)
    points = case_root / "constant" / "polyMesh" / "points"
    compressed = points.with_name("points.gz")
    compressed.write_bytes(gzip.compress(points.read_bytes(), mtime=0))
    points.unlink()

    case = _inspect(case_root, tmp_path / "state")

    execution = case.metadata["inspection_execution"]
    native = case.metadata["openfoam_native"]
    assert execution["backend_id"] == "openfoam.native"
    assert execution["status"] == "success"
    assert native["mesh"]["native_decoded"] is True
    assert native["mesh"]["point_count"] == 8
    assert "constant/polyMesh/points.gz" in execution["paths_accessed"]


def test_invalid_nonuniform_count_degrades_only_affected_field(tmp_path: Path):
    case_root = tmp_path / "field_count_case"
    shutil.copytree(FIXTURE, case_root)
    field = case_root / "1" / "U"
    field.write_text(
        field.read_text(encoding="utf-8").replace("List<vector>\n1\n(", "List<vector>\n2\n("),
        encoding="utf-8",
    )

    case = _inspect(case_root, tmp_path / "state")

    execution = case.metadata["inspection_execution"]
    native = case.metadata["openfoam_native"]
    assert execution["status"] == "partial_success"
    assert native["mesh"]["native_decoded"] is True
    assert native["field_availability"]["1"] == ["U", "p"]
    assert not any(item["name"] == "U" and item["time"] == "1" for item in native["fields"])
    assert any(item.get("code") == "CRX-OF-NATIVE-FIELD-001" for item in case.diagnostics)
