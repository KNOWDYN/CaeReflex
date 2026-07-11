from __future__ import annotations

from pathlib import Path

from caereflex.contracts import InspectionProfile
from caereflex.core.config import CaeReflexConfig
from caereflex.services import inspect_path
from caereflex.spatial import SpatialStore


def test_deep_native_inspection_persists_and_attaches_spatial_graph(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "examples" / "openfoam_cavity_native"
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
    source = Path(__file__).resolve().parents[1] / "examples" / "openfoam_cavity_native"
    case = inspect_path(
        source,
        adapter="openfoam",
        profile=InspectionProfile.standard,
        config=CaeReflexConfig(state_dir=tmp_path / "state"),
    )
    assert not case.metadata.get("spatial_graph_refs")
    assert not case.metadata.get("spatial_mapping")
