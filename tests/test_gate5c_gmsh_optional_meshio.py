from __future__ import annotations

from pathlib import Path

import pytest

from caereflex.arrays import ArrayService
from caereflex.contracts import CaseManifest, InspectionBudget, InspectionProfile, ManifestEntry
from caereflex.execution import execute_inspection_plan
from caereflex.plugins import get_adapter_plugin


@pytest.mark.optional_mesh
def test_optional_meshio_path_decodes_gmsh_mesh_and_data(tmp_path: Path):
    meshio = pytest.importorskip("meshio")
    np = pytest.importorskip("numpy")

    source = tmp_path / "source"
    source.mkdir()
    mesh_path = source / "meshio-square.msh"
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
        cell_data={
            "gmsh:physical": [np.array([2, 2], dtype=int)],
            "gmsh:geometrical": [np.array([1, 1], dtype=int)],
            "quality": [np.array([0.8, 0.9])],
        },
        field_data={"fluid": np.array([2, 2], dtype=int)},
    )
    meshio.write(mesh_path, mesh, file_format="gmsh22", binary=False)

    manifest = CaseManifest(
        manifest_id="manifest_gmsh_meshio_optional",
        root_uri=source.as_uri(),
        entries=[
            ManifestEntry(
                path=mesh_path.name,
                size_bytes=mesh_path.stat().st_size,
                format_hint="gmsh-msh",
                case_hint="gmsh",
            )
        ],
        detected_formats=["gmsh-msh"],
        case_hints=["gmsh"],
    )
    plan = get_adapter_plugin("gmsh").plan(
        manifest,
        InspectionProfile.deep,
        InspectionBudget(max_files=10, max_bytes_read=1024 * 1024, max_wall_time_seconds=10),
    )

    result = execute_inspection_plan(
        manifest,
        plan,
        backend_id="gmsh.native",
        source_root=source,
        state_root=tmp_path / "state",
    )

    assert result.status == "success"
    mesh_summary = result.metadata["backend_result"]["summary"]["files"][0]
    assert mesh_summary.get("reader") == "meshio", result.model_dump_json(indent=2)
    assert mesh_summary["node_count"] == 4
    assert mesh_summary["element_count"] == 2
    assert mesh_summary["bounds"] == [[0.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    assert mesh_summary["physical_groups"] == [
        {"dimension": 2, "tag": 2, "name": "fluid", "element_count": 2}
    ]
    assert {(item["name"], item["association"]) for item in mesh_summary["fields"]} == {
        ("temperature", "point"),
        ("quality", "cell"),
    }
    assert any(attempt.backend_id == "gmsh.meshio" and attempt.outcome == "success" for attempt in result.attempts)

    arrays = ArrayService(tmp_path / "state")
    temperature = next(item for item in mesh_summary["fields"] if item["name"] == "temperature")
    assert arrays.reduce(temperature["array_id"], "mean")["value"] == 25.0
