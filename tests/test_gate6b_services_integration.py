from __future__ import annotations

from pathlib import Path

from caereflex.contracts import InspectionProfile
from caereflex.core.config import CaeReflexConfig
from caereflex.services import inspect_path
from caereflex.spatial import SpatialStore


def _foam_header(class_name: str, object_name: str) -> str:
    return (
        "FoamFile\n{\n"
        "    version 2.0;\n"
        "    format ascii;\n"
        f"    class {class_name};\n"
        f"    object {object_name};\n"
        "}\n"
    )


def _write_case(root: Path) -> Path:
    files = {
        "system/controlDict": _foam_header("dictionary", "controlDict") + "application simpleFoam;\nstartTime 0;\nendTime 0;\n",
        "constant/polyMesh/points": _foam_header("vectorField", "points") + "8\n(\n(0 0 0)\n(1 0 0)\n(1 1 0)\n(0 1 0)\n(0 0 1)\n(1 0 1)\n(1 1 1)\n(0 1 1)\n)\n",
        "constant/polyMesh/faces": _foam_header("faceList", "faces") + "6\n(\n4(0 3 2 1)\n4(4 5 6 7)\n4(0 1 5 4)\n4(1 2 6 5)\n4(2 3 7 6)\n4(3 0 4 7)\n)\n",
        "constant/polyMesh/owner": _foam_header("labelList", "owner") + "6\n(\n0\n0\n0\n0\n0\n0\n)\n",
        "constant/polyMesh/neighbour": _foam_header("labelList", "neighbour") + "0\n(\n)\n",
        "constant/polyMesh/boundary": _foam_header("polyBoundaryMesh", "boundary") + "1\n(\nwalls\n{\ntype wall;\nnFaces 6;\nstartFace 0;\n}\n)\n",
        "0/p": _foam_header("volScalarField", "p") + "dimensions [0 2 -2 0 0 0 0];\ninternalField uniform 0.5;\nboundaryField {}\n",
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_deep_native_inspection_persists_and_attaches_spatial_graph(tmp_path: Path) -> None:
    source = _write_case(tmp_path / "case")
    state = tmp_path / "state"
    case = inspect_path(
        source,
        adapter="openfoam",
        profile=InspectionProfile.deep,
        config=CaeReflexConfig(state_dir=state),
    )

    references = case.metadata.get("spatial_graph_refs")
    reports = case.metadata.get("spatial_mapping")
    assert isinstance(references, list) and len(references) == 1
    assert isinstance(reports, list) and len(reports) == 1
    assert reports[0]["backend_id"] == "openfoam.native"
    assert reports[0]["array_link_count"] > 0

    graph_id = references[0]["graph_id"]
    store = SpatialStore(state)
    snapshot = store.snapshot(graph_id)
    assert snapshot.graph.case_id == case.case_id
    assert snapshot.graph.metadata["cross_format_equivalence_asserted"] is False
    assert any(entity.entity_kind == "patch" for entity in snapshot.entities)
    assert any(link.role == "coordinates" for link in snapshot.array_links)
    assert all(relation.relation_kind != "maps_to" for relation in snapshot.relations)
    assert store.validate_integrity() == []


def test_standard_inspection_does_not_create_spatial_graph(tmp_path: Path) -> None:
    source = _write_case(tmp_path / "case")
    case = inspect_path(
        source,
        adapter="openfoam",
        profile=InspectionProfile.standard,
        config=CaeReflexConfig(state_dir=tmp_path / "state"),
    )
    assert not case.metadata.get("spatial_graph_refs")
    assert not case.metadata.get("spatial_mapping")
