from __future__ import annotations

from pathlib import Path

import pytest

from caereflex.arrays import ArrayService
from caereflex.contracts import CaseManifest, InspectionBudget, InspectionProfile, ManifestEntry
from caereflex.execution import execute_inspection_plan
from caereflex.plugins import get_adapter_plugin


MESHIO_MSH = """$MeshFormat
2.2 0 8
$EndMeshFormat
$PhysicalNames
1
2 2 \"fluid\"
$EndPhysicalNames
$Nodes
4
1 0 0 0
2 1 0 0
3 1 1 0
4 0 1 0
$EndNodes
$Elements
2
1 2 2 2 1 1 2 3
2 2 2 2 1 1 3 4
$EndElements
$NodeData
1
\"temperature\"
1
0.0
3
0
1
4
1 10.0
2 20.0
3 30.0
4 40.0
$EndNodeData
$ElementData
1
\"quality\"
1
0.0
3
0
1
2
1 0.8
2 0.9
$EndElementData
"""


@pytest.mark.optional_mesh
def test_optional_meshio_path_decodes_gmsh_mesh_and_data(tmp_path: Path):
    pytest.importorskip("meshio")

    source = tmp_path / "source"
    source.mkdir()
    mesh_path = source / "meshio-square.msh"
    mesh_path.write_text(MESHIO_MSH, encoding="utf-8")

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
