from __future__ import annotations

from pathlib import Path

from caereflex.arrays import ArrayService
from caereflex.contracts import CaseManifest, InspectionBudget, InspectionPlan, InspectionProfile, ManifestEntry
from caereflex.execution import execute_inspection_plan
from caereflex.plugins import get_adapter_plugin


def _foam_header(class_name: str, object_name: str, *, format_name: str = "ascii") -> str:
    return (
        "FoamFile\n{\n"
        "    version 2.0;\n"
        f"    format {format_name};\n"
        f"    class {class_name};\n"
        f"    object {object_name};\n"
        "}\n"
    )


def _write_case(root: Path, *, include_directive: bool = False) -> list[str]:
    (root / "system").mkdir(parents=True)
    (root / "constant" / "polyMesh").mkdir(parents=True)
    (root / "0").mkdir(parents=True)
    (root / "1").mkdir(parents=True)

    files: dict[str, str] = {
        "system/controlDict": _foam_header("dictionary", "controlDict") + "application simpleFoam;\nstartTime 0;\nendTime 1;\n",
        "constant/transportProperties": _foam_header("dictionary", "transportProperties") + "nu [0 2 -1 0 0 0 0] 0.01;\n",
        "constant/polyMesh/points": _foam_header("vectorField", "points") + "8\n(\n(0 0 0)\n(1 0 0)\n(1 1 0)\n(0 1 0)\n(0 0 1)\n(1 0 1)\n(1 1 1)\n(0 1 1)\n)\n",
        "constant/polyMesh/faces": _foam_header("faceList", "faces") + "6\n(\n4(0 3 2 1)\n4(4 5 6 7)\n4(0 1 5 4)\n4(1 2 6 5)\n4(2 3 7 6)\n4(3 0 4 7)\n)\n",
        "constant/polyMesh/owner": _foam_header("labelList", "owner") + "6\n(\n0\n0\n0\n0\n0\n0\n)\n",
        "constant/polyMesh/neighbour": _foam_header("labelList", "neighbour") + "0\n(\n)\n",
        "constant/polyMesh/boundary": _foam_header("polyBoundaryMesh", "boundary") + "1\n(\nwalls\n{\ntype wall;\nnFaces 6;\nstartFace 0;\n}\n)\n",
        "0/U": _foam_header("volVectorField", "U") + "dimensions [0 1 -1 0 0 0 0];\ninternalField uniform (1 0 0);\nboundaryField {}\n",
        "0/p": _foam_header("volScalarField", "p") + "dimensions [0 2 -2 0 0 0 0];\ninternalField nonuniform List<scalar> 1\n(\n0.5\n);\nboundaryField {}\n",
        "1/U": _foam_header("volVectorField", "U") + "dimensions [0 1 -1 0 0 0 0];\ninternalField uniform (2 0 0);\nboundaryField {}\n",
    }
    if include_directive:
        files["1/U"] = _foam_header("volVectorField", "U") + "#include \"../sharedU\"\ndimensions [0 1 -1 0 0 0 0];\ninternalField uniform (2 0 0);\n"

    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return sorted(files)


def _manifest(root: Path, paths: list[str]) -> CaseManifest:
    return CaseManifest(
        manifest_id="manifest_openfoam_native",
        root_uri=root.as_uri(),
        entries=[ManifestEntry(path=path, size_bytes=(root / path).stat().st_size, case_hint="openfoam") for path in paths],
        detected_formats=["openfoam-case"],
        case_hints=["openfoam"],
    )


def test_native_openfoam_backend_decodes_mesh_fields_and_times(tmp_path: Path):
    source = tmp_path / "case"
    paths = _write_case(source)
    manifest = _manifest(source, paths)
    plugin = get_adapter_plugin("openfoam")
    plan = plugin.plan(
        manifest,
        InspectionProfile.deep,
        InspectionBudget(max_files=100, max_bytes_read=1024 * 1024, max_wall_time_seconds=5),
    )

    result = execute_inspection_plan(
        manifest,
        plan,
        backend_id="openfoam.native",
        source_root=source,
        state_root=tmp_path / "state",
    )

    assert result.status == "success"
    summary = result.metadata["backend_result"]["summary"]
    assert summary["mesh"]["points"] == 8
    assert summary["mesh"]["faces"] == 6
    assert summary["mesh"]["cells"] == 1
    assert summary["mesh"]["internal_faces"] == 0
    assert summary["mesh"]["complete_topology"] is True
    assert summary["mesh"]["bounds"] == [[0.0, 1.0], [0.0, 1.0], [0.0, 1.0]]
    assert summary["patches"] == [{"name": "walls", "type": "wall", "n_faces": 6, "start_face": 0, "physical_type": None}]
    assert summary["time_directories"] == ["0", "1"]
    assert {(field["time"], field["name"]) for field in summary["fields"]} == {("0", "U"), ("0", "p"), ("1", "U")}
    assert summary["array_count"] == len(result.arrays) == 9
    assert result.source_mutation_detected is False

    arrays = ArrayService(tmp_path / "state")
    points_id = summary["mesh"]["points_array_id"]
    assert arrays.describe(points_id)["shape"] == [8, 3]
    assert arrays.reduce(points_id, "max", component=2)["value"] == 1.0
    p_field = next(field for field in summary["fields"] if field["name"] == "p")
    assert arrays.sample(p_field["array_id"], 1)["values"] == [0.5]


def test_openfoam_directive_is_not_executed_and_falls_back(tmp_path: Path):
    source = tmp_path / "case"
    paths = _write_case(source, include_directive=True)
    manifest = _manifest(source, paths)
    plan = get_adapter_plugin("openfoam").plan(
        manifest,
        InspectionProfile.deep,
        InspectionBudget(max_files=100, max_bytes_read=1024 * 1024, max_wall_time_seconds=5),
    )

    result = execute_inspection_plan(
        manifest,
        plan,
        backend_id="openfoam.native",
        source_root=source,
        state_root=tmp_path / "state",
    )

    assert result.status == "success"
    summary = result.metadata["backend_result"]["summary"]
    assert summary["unsupported_directives"] == ["1/U"]
    assert not any(field["time"] == "1" and field["name"] == "U" for field in summary["fields"])
    failed = [attempt for attempt in result.attempts if attempt.outcome == "failed"]
    assert failed
    assert failed[-1].fallback_to == "field-header-and-dimensions"
    assert any(item.code == "CRX-OPENFOAM-FIELD-FALLBACK-001" for item in result.diagnostics)


def test_openfoam_plugin_declares_native_capabilities():
    capabilities = get_adapter_plugin("openfoam").capabilities()
    assert capabilities.plugin_version == "1.2.0"
    assert capabilities.time_series_support is True
    assert capabilities.geometry_support == "native-ascii-points-and-bounds"
    assert capabilities.topology_support == "native-ascii-faces-owner-neighbour-boundary"
    assert capabilities.field_support == "native-ascii-uniform-and-nonuniform-internal-fields"
