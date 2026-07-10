from __future__ import annotations

from pathlib import Path

import pytest

from caereflex.arrays import ArrayService
from caereflex.contracts import (
    CaseManifest,
    ExecutionPolicy,
    InspectionBudget,
    InspectionProfile,
    ManifestEntry,
)
from caereflex.execution import execute_inspection_plan
from caereflex.plugins import get_adapter_plugin


@pytest.mark.optional_vtk
def test_optional_pyvista_path_decodes_binary_vtu_without_mesh_generation(tmp_path: Path):
    pv = pytest.importorskip("pyvista")
    np = pytest.importorskip("numpy")

    source = tmp_path / "source"
    source.mkdir()
    vtk_path = source / "tetra.vtu"
    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )
    cells = np.array([4, 0, 1, 2, 3], dtype=np.int64)
    cell_types = np.array([pv.CellType.TETRA], dtype=np.uint8)
    grid = pv.UnstructuredGrid(cells, cell_types, points)
    grid.point_data["temperature"] = np.array([10.0, 20.0, 30.0, 40.0])
    grid.cell_data["quality"] = np.array([0.95])
    grid.save(vtk_path, binary=True)

    manifest = CaseManifest(
        manifest_id="manifest_vtk_pyvista_optional",
        root_uri=source.as_uri(),
        entries=[ManifestEntry(
            path=vtk_path.name,
            size_bytes=vtk_path.stat().st_size,
            format_hint="vtk-xml",
            case_hint="vtk",
        )],
        detected_formats=["vtk-xml"],
        case_hints=["vtk"],
    )
    plan = get_adapter_plugin("vtk").plan(
        manifest,
        InspectionProfile.deep,
        InspectionBudget(max_files=10, max_bytes_read=5 * 1024 * 1024, max_wall_time_seconds=20),
    )

    result = execute_inspection_plan(
        manifest,
        plan,
        backend_id="vtk.native",
        source_root=source,
        state_root=tmp_path / "state",
        backend_options={"disable_meshio": True},
        policy=ExecutionPolicy(max_memory_bytes=4 * 1024 * 1024 * 1024),
    )

    assert result.status == "success"
    pyvista_attempts = [
        {
            "outcome": attempt.outcome,
            "exception_type": attempt.exception_type,
            "exception_message": attempt.exception_message,
            "metadata": attempt.metadata,
        }
        for attempt in result.attempts
        if attempt.backend_id == "vtk.pyvista"
    ]
    assert pyvista_attempts and pyvista_attempts[-1]["outcome"] == "success", pyvista_attempts
    dataset = result.metadata["backend_result"]["summary"]["files"][0]
    assert dataset.get("reader") == "vtk.pyvista"
    assert dataset["point_count"] == 4
    assert dataset["cell_count"] == 1
    assert dataset["dimension"] == 3
    assert dataset["bounds"] == [[0.0, 1.0], [0.0, 1.0], [0.0, 1.0]]
    assert {(item["name"], item["association"]) for item in dataset["fields"]} == {
        ("temperature", "point"),
        ("quality", "cell"),
    }
    assert result.source_mutation_detected is False

    arrays = ArrayService(tmp_path / "state")
    quality = next(item for item in dataset["fields"] if item["name"] == "quality")
    assert arrays.sample(quality["array_id"], 1)["values"] == [0.95]
