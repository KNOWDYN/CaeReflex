from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from caereflex.contracts import (
    CaseManifest,
    InspectionBudget,
    InspectionPlan,
    InspectionProfile,
    ManifestEntry,
)
from caereflex.execution import execute_inspection_plan


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(
    tmp_path: Path,
    *,
    name: str,
    plugin_id: str,
    backend_id: str,
    relative_path: str,
    payload: bytes,
    backend_options: dict[str, Any] | None = None,
):
    source = tmp_path / f"source-{name}"
    path = source / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    before = _digest(path)
    manifest = CaseManifest(
        manifest_id=f"manifest_{name}",
        root_uri=source.as_uri(),
        entries=[
            ManifestEntry(
                path=relative_path,
                size_bytes=path.stat().st_size,
                case_hint=plugin_id,
            )
        ],
        case_hints=[plugin_id],
    )
    plan = InspectionPlan(
        plugin_id=plugin_id,
        profile=InspectionProfile.forensic,
        selected_paths=[relative_path],
        backend_candidates=[backend_id],
        operation=f"malformed_{name}",
        budget=InspectionBudget(
            max_files=5,
            max_bytes_read=1024 * 1024,
            max_wall_time_seconds=15,
        ),
    )
    result = execute_inspection_plan(
        manifest,
        plan,
        backend_id=backend_id,
        source_root=source,
        state_root=tmp_path / f"state-{name}",
        backend_options=backend_options,
    )
    assert _digest(path) == before
    assert result.source_mutation_detected is False
    return result


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        (
            "gmsh-binary-header",
            b"$MeshFormat\n2.2 1 8\n$EndMeshFormat\n\x00binary\n",
        ),
        (
            "gmsh-truncated-nodes",
            b"$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n3\n1 0 0 0\n$EndNodes\n",
        ),
        (
            "gmsh-duplicate-node-tags",
            b"$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n2\n1 0 0 0\n1 1 0 0\n$EndNodes\n$Elements\n0\n$EndElements\n",
        ),
        (
            "gmsh-unclosed-section",
            b"$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n1\n1 0 0 0\n",
        ),
    ],
)
def test_malformed_gmsh_inputs_fall_back_without_worker_crash(
    tmp_path: Path,
    name: str,
    payload: bytes,
):
    result = _run(
        tmp_path,
        name=name,
        plugin_id="gmsh",
        backend_id="gmsh.native",
        relative_path="broken.msh",
        payload=payload,
        backend_options={"disable_meshio": True},
    )

    assert result.status == "success"
    summary = result.metadata["backend_result"]["summary"]
    file_summary = summary["files"][0]
    assert file_summary["status"] == "fingerprinted"
    assert file_summary["decoded"] is False
    assert summary["gate5_compatibility"]["evidence_status"] == "fallback_only"
    assert any(item.code == "CRX-GMSH-MSH-FALLBACK-001" for item in result.diagnostics)
    assert any(item.outcome == "failed" for item in result.attempts)
    assert not result.arrays


def _foam_header(class_name: str, object_name: str, format_name: str = "ascii") -> bytes:
    return (
        "FoamFile\n{\n"
        "version 2.0;\n"
        f"format {format_name};\n"
        f"class {class_name};\n"
        f"object {object_name};\n"
        "}\n"
    ).encode("utf-8")


@pytest.mark.parametrize(
    ("name", "relative_path", "payload"),
    [
        (
            "openfoam-points-count-mismatch",
            "constant/polyMesh/points",
            _foam_header("vectorField", "points") + b"2\n(\n(0 0 0)\n)\n",
        ),
        (
            "openfoam-binary-points",
            "constant/polyMesh/points",
            _foam_header("vectorField", "points", "binary") + b"1\n(\n\x00\x01\x02\n)\n",
        ),
        (
            "openfoam-negative-owner",
            "constant/polyMesh/owner",
            _foam_header("labelList", "owner") + b"1\n(\n-1\n)\n",
        ),
        (
            "openfoam-unclosed-faces",
            "constant/polyMesh/faces",
            _foam_header("faceList", "faces") + b"1\n(\n3(0 1 2)\n",
        ),
    ],
)
def test_malformed_openfoam_inputs_degrade_without_worker_crash(
    tmp_path: Path,
    name: str,
    relative_path: str,
    payload: bytes,
):
    result = _run(
        tmp_path,
        name=name,
        plugin_id="openfoam",
        backend_id="openfoam.native",
        relative_path=relative_path,
        payload=payload,
    )

    assert result.status == "success"
    summary = result.metadata["backend_result"]["summary"]
    assert summary["gate5_compatibility"]["evidence_status"] == "fallback_only"
    assert any(item.code == "CRX-OPENFOAM-NATIVE-FALLBACK-001" for item in result.diagnostics)
    assert any(item.outcome == "failed" for item in result.attempts)
    assert not result.arrays


@pytest.mark.parametrize(
    ("name", "relative_path", "payload", "diagnostic_codes"),
    [
        (
            "vtk-binary-legacy",
            "broken.vtk",
            b"# vtk DataFile Version 3.0\nbinary fixture\nBINARY\nDATASET POLYDATA\n",
            {"CRX-VTK-CORE-FALLBACK-001"},
        ),
        (
            "vtk-truncated-points",
            "broken.vtk",
            b"# vtk DataFile Version 3.0\ntruncated fixture\nASCII\nDATASET POLYDATA\nPOINTS 3 float\n0 0 0\n1 0 0\n",
            {"CRX-VTK-CORE-FALLBACK-001"},
        ),
        (
            "vtk-invalid-cell-count",
            "broken.vtk",
            b"# vtk DataFile Version 3.0\ncell fixture\nASCII\nDATASET POLYDATA\nPOINTS 3 float\n0 0 0\n1 0 0\n0 1 0\nPOLYGONS 1 4\n-3 0 1 2\n",
            {"CRX-VTK-CORE-FALLBACK-001"},
        ),
        (
            "vtk-truncated-xml",
            "broken.vtu",
            b"<?xml version='1.0'?><VTKFile type='UnstructuredGrid'><UnstructuredGrid>",
            {"CRX-VTK-CORE-FALLBACK-001"},
        ),
        (
            "vtk-appended-xml",
            "broken.vtu",
            b"<?xml version='1.0'?><VTKFile type='UnstructuredGrid'><UnstructuredGrid><Piece NumberOfPoints='0' NumberOfCells='0'/></UnstructuredGrid><AppendedData encoding='raw'>_x</AppendedData></VTKFile>",
            {"CRX-VTK-XML-ENCODING-001", "CRX-VTK-CORE-FALLBACK-001"},
        ),
    ],
)
def test_malformed_vtk_inputs_fall_back_without_worker_crash(
    tmp_path: Path,
    name: str,
    relative_path: str,
    payload: bytes,
    diagnostic_codes: set[str],
):
    result = _run(
        tmp_path,
        name=name,
        plugin_id="vtk",
        backend_id="vtk.native",
        relative_path=relative_path,
        payload=payload,
        backend_options={"disable_pyvista": True, "disable_meshio": True},
    )

    assert result.status == "success"
    summary = result.metadata["backend_result"]["summary"]
    file_summary = summary["files"][0]
    assert file_summary["status"] == "fingerprinted"
    assert file_summary["decoded"] is False
    assert summary["gate5_compatibility"]["evidence_status"] == "fallback_only"
    assert diagnostic_codes & {item.code for item in result.diagnostics}
    assert any(item.outcome == "failed" for item in result.attempts)
    assert not result.arrays


@pytest.mark.parametrize(
    "mode",
    [
        "invalid_payload",
        "missing_summary_payload",
        "nonfinite_payload",
        "absolute_path_payload",
        "traversal_path_payload",
        "heavy_payload",
        "mismatched_array_count_payload",
        "mismatched_diagnostic_count_payload",
    ],
)
def test_worker_rejects_backend_contract_violations_deterministically(
    tmp_path: Path,
    monkeypatch,
    mode: str,
):
    monkeypatch.setenv("CAEREFLEX_ENABLE_TEST_BACKENDS", "1")
    result = _run(
        tmp_path,
        name=f"contract-{mode}",
        plugin_id="fixture",
        backend_id="test.execution",
        relative_path="input.dat",
        payload=b"fixture",
        backend_options={"mode": mode},
    )

    assert result.status == "failed"
    assert result.worker_exit_code == 1
    assert result.termination_reason
    assert any(item.code == "CRX-GATE5-COMPAT-001" for item in result.diagnostics)
    assert any(item.exception_type == "BackendCompatibilityError" for item in result.attempts)
    assert "backend_result" not in result.metadata
