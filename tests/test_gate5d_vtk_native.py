from __future__ import annotations

from pathlib import Path

from caereflex.arrays import ArrayService
from caereflex.contracts import CaseManifest, InspectionBudget, InspectionProfile, ManifestEntry
from caereflex.core.config import CaeReflexConfig
from caereflex.execution import execute_inspection_plan, list_execution_backends
from caereflex.plugins import get_adapter_plugin
from caereflex.services import inspect_path


LEGACY_VTK = """# vtk DataFile Version 3.0
Gate 5D fixture
ASCII
DATASET UNSTRUCTURED_GRID
POINTS 4 double
0 0 0
1 0 0
1 1 0
0 1 0
CELLS 2 8
3 0 1 2
3 0 2 3
CELL_TYPES 2
5 5
POINT_DATA 4
SCALARS pressure double 1
LOOKUP_TABLE default
0.0 0.1 0.2 0.1
VECTORS velocity double
0 0 0
1 0 0
1 1 0
0 1 0
CELL_DATA 2
SCALARS quality double 1
LOOKUP_TABLE default
0.8 0.9
FIELD FieldData 1
time 1 1 double
2.5
"""

VTU_ASCII = """<?xml version="1.0"?>
<VTKFile type="UnstructuredGrid" version="1.0" byte_order="LittleEndian" header_type="UInt32">
  <UnstructuredGrid>
    <Piece NumberOfPoints="4" NumberOfCells="2">
      <PointData>
        <DataArray type="Float64" Name="temperature" format="ascii">10 20 30 40</DataArray>
        <DataArray type="Float64" Name="velocity" NumberOfComponents="3" format="ascii">0 0 0 1 0 0 1 1 0 0 1 0</DataArray>
      </PointData>
      <CellData><DataArray type="Float64" Name="quality" format="ascii">0.8 0.9</DataArray></CellData>
      <FieldData><DataArray type="Float64" Name="time" format="ascii">1.5</DataArray></FieldData>
      <Points><DataArray type="Float64" NumberOfComponents="3" format="ascii">0 0 0 1 0 0 1 1 0 0 1 0</DataArray></Points>
      <Cells>
        <DataArray type="Int64" Name="connectivity" format="ascii">0 1 2 0 2 3</DataArray>
        <DataArray type="Int64" Name="offsets" format="ascii">3 6</DataArray>
        <DataArray type="UInt8" Name="types" format="ascii">5 5</DataArray>
      </Cells>
    </Piece>
  </UnstructuredGrid>
</VTKFile>
"""

APPENDED_VTU = """<?xml version="1.0"?>
<VTKFile type="UnstructuredGrid" version="1.0" byte_order="LittleEndian" header_type="UInt32">
  <UnstructuredGrid><Piece NumberOfPoints="1" NumberOfCells="0">
    <Points><DataArray type="Float32" NumberOfComponents="3" format="appended" offset="0"/></Points>
  </Piece></UnstructuredGrid>
  <AppendedData encoding="base64">_AAAAAA==</AppendedData>
</VTKFile>
"""

PVD = """<?xml version="1.0"?>
<VTKFile type="Collection" version="1.0" byte_order="LittleEndian">
  <Collection>
    <DataSet timestep="0.0" group="" part="0" file="step0.vtu"/>
    <DataSet timestep="1.0" group="" part="0" file="step1.vtu"/>
    <DataSet timestep="2.0" group="" part="0" file="../outside.vtu"/>
  </Collection>
</VTKFile>
"""


def _format_hint(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".vtk":
        return "vtk-legacy"
    if suffix in {".pvd", ".vtm", ".vtmb"}:
        return "vtk-collection"
    return "vtk-xml"


def _manifest(root: Path, paths: list[str]) -> CaseManifest:
    return CaseManifest(
        manifest_id="manifest_vtk_native",
        root_uri=root.as_uri(),
        entries=[
            ManifestEntry(
                path=path,
                size_bytes=(root / path).stat().st_size,
                format_hint=_format_hint(path),
                case_hint="vtk",
            )
            for path in paths
        ],
        detected_formats=sorted({_format_hint(path) for path in paths}),
        case_hints=["vtk"],
    )


def _execute(root: Path, paths: list[str], state: Path):
    manifest = _manifest(root, paths)
    plan = get_adapter_plugin("vtk").plan(
        manifest,
        InspectionProfile.deep,
        InspectionBudget(max_files=20, max_bytes_read=2 * 1024 * 1024, max_wall_time_seconds=10),
    )
    return execute_inspection_plan(
        manifest,
        plan,
        backend_id="vtk.native",
        source_root=root,
        state_root=state,
        backend_options={"disable_pyvista": True, "disable_meshio": True},
    )


def test_legacy_ascii_vtk_decodes_topology_fields_and_lazy_arrays(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "mesh.vtk").write_text(LEGACY_VTK, encoding="utf-8")
    result = _execute(source, ["mesh.vtk"], tmp_path / "state")

    assert result.status == "success"
    assert result.source_mutation_detected is False
    dataset = result.metadata["backend_result"]["summary"]["files"][0]
    assert dataset["reader"] == "vtk.core"
    assert dataset["dataset_type"] == "UNSTRUCTURED_GRID"
    assert dataset["point_count"] == 4
    assert dataset["cell_count"] == 2
    assert dataset["dimension"] == 2
    assert dataset["bounds"] == [[0.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    assert dataset["cell_types"] == [{"vtk_type": 5, "name": "triangle", "dimension": 2, "count": 2}]
    assert {(field["name"], field["association"], field["components"]) for field in dataset["fields"]} == {
        ("pressure", "point", 1), ("velocity", "point", 3),
        ("quality", "cell", 1), ("time", "field", 1),
    }
    assert any(attempt.backend_id == "vtk.core" and attempt.outcome == "success" for attempt in result.attempts)

    arrays = ArrayService(tmp_path / "state")
    points_id = dataset["arrays"]["points_array_id"]
    assert arrays.describe(points_id)["shape"] == [4, 3]
    assert arrays.reduce(points_id, "max", component=1)["value"] == 1.0
    pressure = next(field for field in dataset["fields"] if field["name"] == "pressure")
    assert arrays.reduce(pressure["array_id"], "mean")["value"] == 0.1
    velocity = next(field for field in dataset["fields"] if field["name"] == "velocity")
    sample = arrays.sample(velocity["array_id"], 3)
    assert sample["indices"] == [0, 6, 11]
    assert sample["values"] == [0.0, 1.0, 0.0]


def test_xml_vtu_decodes_points_cells_and_all_field_associations(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "mesh.vtu").write_text(VTU_ASCII, encoding="utf-8")
    result = _execute(source, ["mesh.vtu"], tmp_path / "state")

    assert result.status == "success"
    dataset = result.metadata["backend_result"]["summary"]["files"][0]
    assert dataset["reader"] == "vtk.core"
    assert dataset["dataset_type"] == "UnstructuredGrid"
    assert dataset["point_count"] == 4
    assert dataset["cell_count"] == 2
    assert dataset["dimension"] == 2
    assert dataset["bounds"] == [[0.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
    assert {(field["name"], field["association"]) for field in dataset["fields"]} == {
        ("temperature", "point"), ("velocity", "point"),
        ("quality", "cell"), ("time", "field"),
    }
    arrays = ArrayService(tmp_path / "state")
    temperature = next(field for field in dataset["fields"] if field["name"] == "temperature")
    assert arrays.reduce(temperature["array_id"], "mean")["value"] == 25.0
    assert arrays.describe(dataset["arrays"]["cell_connectivity_array_id"])["shape"] == [6]


def test_pvd_inventory_reports_times_and_blocks_unsafe_references(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "series.pvd").write_text(PVD, encoding="utf-8")
    (source / "step0.vtu").write_text(VTU_ASCII, encoding="utf-8")
    (source / "step1.vtu").write_text(VTU_ASCII, encoding="utf-8")
    result = _execute(source, ["series.pvd", "step0.vtu", "step1.vtu"], tmp_path / "state")

    assert result.status == "success"
    summary = result.metadata["backend_result"]["summary"]
    collection = next(item for item in summary["files"] if item["source_path"] == "series.pvd")
    assert collection["reader"] == "vtk.xml-inventory"
    assert collection["external_references_loaded"] is False
    assert collection["time_values"] == [0.0, 1.0, 2.0]
    assert summary["time_values"] == [0.0, 1.0, 2.0]
    assert collection["references"][0]["selected"] is True
    assert collection["references"][1]["selected"] is True
    assert collection["references"][2]["safe"] is False
    assert any(item.code == "CRX-VTK-COLLECTION-REFERENCE-001" for item in result.diagnostics)


def test_appended_xml_falls_back_to_fingerprint_without_parent_failure(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "appended.vtu").write_text(APPENDED_VTU, encoding="utf-8")
    result = _execute(source, ["appended.vtu"], tmp_path / "state")

    assert result.status == "success"
    dataset = result.metadata["backend_result"]["summary"]["files"][0]
    assert dataset["status"] == "fingerprinted"
    assert dataset["decoded"] is False
    assert any(item.code == "CRX-VTK-XML-ENCODING-001" for item in result.diagnostics)
    assert [attempt for attempt in result.attempts if attempt.outcome == "failed"][-1].fallback_to == "fingerprint-only"


def test_deep_vtk_inspection_is_integrated_with_reflexcase(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "mesh.vtk").write_text(LEGACY_VTK, encoding="utf-8")
    case = inspect_path(
        source / "mesh.vtk",
        adapter="vtk",
        profile="deep",
        config=CaeReflexConfig(state_dir=tmp_path / "state"),
    )

    assert case.metadata["inspection_execution"]["backend_id"] == "vtk.native"
    assert case.metadata["native_vtk"]["dataset_count"] == 1
    assert case.metadata["native_vtk"]["files"][0]["point_count"] == 4
    assert case.array_references


def test_vtk_plugin_and_backend_declare_native_capability():
    capabilities = get_adapter_plugin("vtk").capabilities()
    assert capabilities.plugin_version == "1.2.0"
    assert capabilities.time_series_support is True
    assert capabilities.geometry_support == "points-bounds-structured-extents-and-rectilinear-coordinates"
    assert capabilities.topology_support == "pyvista-meshio-and-core-legacy-xml-connectivity"
    assert capabilities.field_support == "point-cell-field-data-with-lazy-array-references"
    assert "vtk.native" in {item["backend_id"] for item in list_execution_backends()}
