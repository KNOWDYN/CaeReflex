from __future__ import annotations

from pathlib import Path

from caereflex.arrays import ArrayService
from caereflex.contracts import CaseManifest, InspectionBudget, InspectionProfile, ManifestEntry
from caereflex.core.config import CaeReflexConfig
from caereflex.execution import execute_inspection_plan
from caereflex.plugins import get_adapter_plugin
from caereflex.services import inspect_path


MSH_V2 = """$MeshFormat
2.2 0 8
$EndMeshFormat
$PhysicalNames
2
1 1 \"walls\"
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
6
1 1 2 1 1 1 2
2 1 2 1 2 2 3
3 1 2 1 3 3 4
4 1 2 1 4 4 1
5 2 2 2 1 1 2 3
6 2 2 2 1 1 3 4
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
1 10
2 20
3 30
4 40
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
5 0.8
6 0.9
$EndElementData
"""

MSH_V4 = """$MeshFormat
4.1 0 8
$EndMeshFormat
$PhysicalNames
1
2 1 \"surface\"
$EndPhysicalNames
$Entities
0 0 1 0
1 0 0 0 1 1 0 1 1 0
$EndEntities
$Nodes
1 4 1 4
2 1 0 4
1
2
3
4
0 0 0
1 0 0
1 1 0
0 1 0
$EndNodes
$Elements
1 2 1 2
2 1 2 2
1 1 2 3
2 1 3 4
$EndElements
"""


def _manifest(root: Path, paths: list[str]) -> CaseManifest:
    return CaseManifest(
        manifest_id="manifest_gmsh_native",
        root_uri=root.as_uri(),
        entries=[
            ManifestEntry(
                path=path,
                size_bytes=(root / path).stat().st_size,
                format_hint="gmsh-msh" if path.endswith(".msh") else "gmsh-geo",
                case_hint="gmsh",
            )
            for path in paths
        ],
        detected_formats=["gmsh-msh" if any(path.endswith(".msh") for path in paths) else "gmsh-geo"],
        case_hints=["gmsh"],
    )


def _execute(root: Path, paths: list[str], state: Path):
    manifest = _manifest(root, paths)
    plan = get_adapter_plugin("gmsh").plan(
        manifest,
        InspectionProfile.deep,
        InspectionBudget(max_files=20, max_bytes_read=1024 * 1024, max_wall_time_seconds=5),
    )
    return execute_inspection_plan(
        manifest,
        plan,
        backend_id="gmsh.native",
        source_root=root,
        state_root=state,
        backend_options={"disable_meshio": True},
    )


def test_native_gmsh_v2_decodes_mesh_physical_groups_and_fields(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "square.msh").write_text(MSH_V2, encoding="utf-8")

    result = _execute(source, ["square.msh"], tmp_path / "state")

    assert result.status == "success"
    summary = result.metadata["backend_result"]["summary"]
    mesh = summary["files"][0]
    assert mesh["reader"] == "gmsh.core-ascii"
    assert mesh["mesh_format_version"] == "2.2"
    assert mesh["dimension"] == 2
    assert mesh["node_count"] == 4
    assert mesh["element_count"] == 6
    assert mesh["bounds"] == [[0.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    assert {(group["name"], group["element_count"]) for group in mesh["physical_groups"]} == {
        ("walls", 4),
        ("fluid", 2),
    }
    assert {(field["name"], field["association"]) for field in mesh["fields"]} == {
        ("temperature", "point"),
        ("quality", "cell"),
    }
    assert result.source_mutation_detected is False
    assert any(attempt.backend_id == "gmsh.core-ascii" and attempt.outcome == "success" for attempt in result.attempts)

    arrays = ArrayService(tmp_path / "state")
    points_id = mesh["arrays"]["points_array_id"]
    assert arrays.describe(points_id)["shape"] == [4, 3]
    assert arrays.reduce(points_id, "max", component=1)["value"] == 1.0
    temperature = next(field for field in mesh["fields"] if field["name"] == "temperature")
    assert arrays.reduce(temperature["array_id"], "mean")["value"] == 25.0


def test_native_gmsh_v4_decodes_entities_and_physical_membership(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "surface.msh").write_text(MSH_V4, encoding="utf-8")

    result = _execute(source, ["surface.msh"], tmp_path / "state")

    assert result.status == "success"
    mesh = result.metadata["backend_result"]["summary"]["files"][0]
    assert mesh["mesh_format_version"] == "4.1"
    assert mesh["node_count"] == 4
    assert mesh["element_count"] == 2
    assert mesh["entities"] == [
        {
            "dimension": 2,
            "tag": 1,
            "bounds": [0.0, 0.0, 0.0, 1.0, 1.0, 0.0],
            "physical_tags": [1],
            "bounding_tags": [],
        }
    ]
    assert mesh["physical_groups"] == [
        {"dimension": 2, "tag": 1, "name": "surface", "element_count": 2}
    ]


def test_geo_is_parsed_as_declarations_and_never_executed(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    geo = source / "model.geo"
    geo.write_text(
        "lc = 0.1;\n"
        "Point(1) = {0, 0, 0, lc};\n"
        "Point(2) = {1, 0, 0, lc};\n"
        "Line(1) = {1, 2};\n"
        "Curve Loop(1) = {1};\n"
        "Plane Surface(1) = {1};\n"
        "Physical Curve(\"wall\", 10) = {1};\n"
        "Include \"must-not-be-opened.geo\";\n"
        "SystemCall \"touch forbidden\";\n",
        encoding="utf-8",
    )

    result = _execute(source, ["model.geo"], tmp_path / "state")

    assert result.status == "success"
    geometry = result.metadata["backend_result"]["summary"]["files"][0]
    assert geometry["reader"] == "gmsh.geo-declaration-parser"
    assert geometry["executed"] is False
    assert geometry["point_count"] == 2
    assert geometry["dimension"] == 2
    assert geometry["physical_groups"][0]["name"] == "wall"
    assert geometry["unsupported_constructs"] == ["Include", "SystemCall"]
    assert any(item.code == "CRX-GMSH-GEO-PARTIAL-001" for item in result.diagnostics)
    assert not (source / "must-not-be-opened.geo").exists()
    assert not (source / "forbidden").exists()


def test_binary_mesh_falls_back_to_fingerprint_without_parent_failure(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "binary.msh").write_bytes(b"$MeshFormat\n4.1 1 8\n$EndMeshFormat\n\x00")

    result = _execute(source, ["binary.msh"], tmp_path / "state")

    assert result.status == "success"
    file_summary = result.metadata["backend_result"]["summary"]["files"][0]
    assert file_summary["status"] == "fingerprinted"
    assert file_summary["decoded"] is False
    assert any(item.code == "CRX-GMSH-MSH-FALLBACK-001" for item in result.diagnostics)
    failed = [attempt for attempt in result.attempts if attempt.outcome == "failed"]
    assert failed[-1].fallback_to == "fingerprint-only"


def test_deep_gmsh_inspection_is_integrated_with_reflexcase(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "square.msh").write_text(MSH_V2, encoding="utf-8")
    config = CaeReflexConfig(state_dir=tmp_path / "state")

    case = inspect_path(source / "square.msh", adapter="gmsh", profile="deep", config=config)

    assert case.metadata["inspection_execution"]["backend_id"] == "gmsh.native"
    assert case.metadata["native_gmsh"]["mesh_count"] == 1
    assert case.metadata["native_gmsh"]["files"][0]["node_count"] == 4
    assert case.array_references


def test_gmsh_plugin_declares_native_capabilities():
    capabilities = get_adapter_plugin("gmsh").capabilities()
    assert capabilities.plugin_version == "1.2.0"
    assert capabilities.time_series_support is True
    assert capabilities.geometry_support == "safe-geo-declarations-and-optional-explicit-gmsh-api"
    assert capabilities.topology_support == "meshio-first-and-core-ascii-msh-2x-4x"
    assert capabilities.field_support == "node-data-element-data-and-meshio-point-cell-data"
