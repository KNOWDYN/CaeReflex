from __future__ import annotations

from pathlib import Path

import pytest

from caereflex.arrays import ArrayService
from caereflex.contracts import CaseManifest, InspectionBudget, InspectionProfile, ManifestEntry
from caereflex.execution import execute_inspection_plan
from caereflex.plugins import get_adapter_plugin


@pytest.mark.optional_mesh
def test_optional_meshio_path_decodes_vtu_mesh_and_data(tmp_path: Path):
    meshio = pytest.importorskip("meshio")
    np = pytest.importorskip("numpy")

    source = tmp_path / "source"
    source.mkdir()
    vtk_path = source / "meshio-square.vtu"
    mesh = meshio.Mesh(
        points=np.array(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
            ]
        ),
        cells=[("triangle", np.array([[0, 1, 2], [0, 2, 3]], dtype=int))],
        point_data={"temperature": np.array([10.0, 20.0, 30.0, 40.0])},
        cell_data={"quality": [np.array([0.8, 0.9])]},
    )
    meshio.write(vtk_path, mesh, file_format="vtu", binary=False)

    manifest = CaseManifest(
        manifest_id="manifest_vtk_meshio_optional",
        root_uri=source.as_uri(),
        entries=[
            ManifestEntry(
                path=vtk_path.name,
                size_bytes=vtk_path.stat().st_size,
                format_hint="vtk-xml",
                case_hint="vtk",
            )
        ],
        detected_formats=["vtk-xml"],
        case_hints=["vtk"],
    )
    plan = get_adapter_plugin("vtk").plan(
        manifest,
        InspectionProfile.deep,
        InspectionBudget(max_files=10, max_bytes_read=2 * 1024 * 1024, max_wall_time_seconds=15),
    )

    result = execute_inspection_plan(
        manifest,
        plan,
        backend_id="vtk.native",
        source_root=source,
        state_root=tmp_path / "state",
        backend_options={"disable_pyvista": True},
    )

    assert result.status == "success"
    dataset = result.metadata["backend_result"]["summary"]["files"][0]
    assert dataset["reader"] == "vtk.meshio"
    assert dataset["point_count"] == 4
    assert dataset["cell_count"] == 2
    assert dataset["bounds"] == [[0.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    assert {(item["name"], item["association"]) for item in dataset["fields"]} == {
        ("temperature", "point"),
        ("quality", "cell"),
    }
    assert any(attempt.backend_id == "vtk.meshio" and attempt.outcome == "success" for attempt in result.attempts)

    arrays = ArrayService(tmp_path / "state")
    temperature = next(item for item in dataset["fields"] if item["name"] == "temperature")
    assert arrays.reduce(temperature["array_id"], "mean")["value"] == 25.0
