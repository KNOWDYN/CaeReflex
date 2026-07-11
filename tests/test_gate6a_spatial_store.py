import json
import sqlite3
from pathlib import Path

import pytest

from caereflex.arrays import ArrayService
from caereflex.contracts import CONTRACT_VERSION
from caereflex.core.models import ReflexCase
from caereflex.spatial import (
    CoordinateFrame,
    CoordinateHandedness,
    SpatialArrayLink,
    SpatialArrayRole,
    SpatialEntity,
    SpatialEntityKind,
    SpatialEvidenceStatus,
    SpatialGraph,
    SpatialGraphSnapshot,
    SpatialGraphStatus,
    SpatialRelation,
    SpatialRelationKind,
    SpatialStore,
    SpatialStoreError,
    attach_spatial_graph_ref,
)


def world_frame() -> CoordinateFrame:
    return CoordinateFrame(
        frame_id="frame_world",
        name="World",
        dimension=3,
        origin=(0.0, 0.0, 0.0),
        basis=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        handedness=CoordinateHandedness.right,
        length_unit="m",
        length_unit_status=SpatialEvidenceStatus.explicit,
        evidence_status=SpatialEvidenceStatus.explicit,
        confidence=1.0,
    )


def build_snapshot(state_root: Path) -> SpatialGraphSnapshot:
    arrays = ArrayService(state_root)
    coordinates = arrays.register_numeric(
        [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
        dtype="float64",
        shape=(2, 3),
        source_asset_id="asset_mesh",
        association="point",
        component_names=["x", "y", "z"],
        coordinate_frame_ref="frame_world",
    )
    frame = world_frame()
    surface = SpatialEntity(
        entity_id="surface_wall",
        entity_kind=SpatialEntityKind.geometry_surface,
        embedding_dimension=3,
        coordinate_frame_id=frame.frame_id,
        evidence_status=SpatialEvidenceStatus.explicit,
    )
    mesh_face = SpatialEntity(
        entity_id="mesh_face_wall",
        entity_kind=SpatialEntityKind.mesh_face,
        embedding_dimension=3,
        coordinate_frame_id=frame.frame_id,
        evidence_status=SpatialEvidenceStatus.explicit,
    )
    relation = SpatialRelation(
        relation_id="rel_mesh_discretises_surface",
        relation_kind=SpatialRelationKind.discretises,
        source_entity_id=mesh_face.entity_id,
        target_entity_id=surface.entity_id,
        evidence_status=SpatialEvidenceStatus.explicit,
    )
    link = SpatialArrayLink.from_array_ref(
        coordinates,
        link_id="link_mesh_face_coordinates",
        role=SpatialArrayRole.coordinates,
        owner_entity_id=mesh_face.entity_id,
        coordinate_frame_id=frame.frame_id,
    )
    graph = SpatialGraph(
        graph_id="graph_case_1",
        case_id="case_1",
        default_coordinate_frame_id=frame.frame_id,
        status=SpatialGraphStatus.draft,
    )
    return SpatialGraphSnapshot(
        graph=graph,
        coordinate_frames=[frame],
        entities=[surface, mesh_face],
        relations=[relation],
        array_links=[link],
    )


def test_snapshot_round_trip_and_compact_statistics(tmp_path: Path):
    state_root = tmp_path / "state"
    snapshot = build_snapshot(state_root)
    store = SpatialStore(state_root)

    reference = store.put_snapshot(snapshot)

    assert reference.contract_version == CONTRACT_VERSION
    assert reference.frame_count == 1
    assert reference.entity_count == 2
    assert reference.relation_count == 1
    assert reference.array_link_count == 1
    assert reference.default_coordinate_frame_id == "frame_world"
    assert reference.store_uri == "caereflex-spatial://sqlite/graph_case_1"

    restored = store.snapshot("graph_case_1")
    assert [item.frame_id for item in restored.coordinate_frames] == ["frame_world"]
    assert [item.entity_id for item in restored.entities] == ["mesh_face_wall", "surface_wall"]
    assert [item.relation_id for item in restored.relations] == ["rel_mesh_discretises_surface"]
    assert [item.link_id for item in restored.array_links] == ["link_mesh_face_coordinates"]
    assert store.validate_integrity() == []


def test_spatial_database_keeps_heavy_values_outside_metadata_tables(tmp_path: Path):
    state_root = tmp_path / "state"
    snapshot = build_snapshot(state_root)
    store = SpatialStore(state_root)
    store.put_snapshot(snapshot)

    with sqlite3.connect(store.database_path) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM spatial_array_links"
        ).fetchall()
        column_types = {
            row[2].upper()
            for table in (
                "spatial_graphs",
                "spatial_coordinate_frames",
                "spatial_entities",
                "spatial_relations",
                "spatial_array_links",
            )
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }

    payload = json.loads(rows[0][0])
    assert "values" not in payload
    assert "coordinates" not in payload
    assert payload["array_id"].startswith("array_")
    assert "BLOB" not in column_types


def test_unknown_array_rolls_back_entire_snapshot(tmp_path: Path):
    state_root = tmp_path / "state"
    frame = world_frame()
    entity = SpatialEntity(
        entity_id="mesh_nodes",
        entity_kind=SpatialEntityKind.mesh_node,
        embedding_dimension=3,
        coordinate_frame_id=frame.frame_id,
    )
    snapshot = SpatialGraphSnapshot(
        graph=SpatialGraph(
            graph_id="graph_bad_array",
            case_id="case_bad",
            default_coordinate_frame_id=frame.frame_id,
        ),
        coordinate_frames=[frame],
        entities=[entity],
        array_links=[
            SpatialArrayLink(
                link_id="link_unknown",
                array_id="array_not_registered",
                role=SpatialArrayRole.coordinates,
                owner_entity_id=entity.entity_id,
                coordinate_frame_id=frame.frame_id,
            )
        ],
    )
    store = SpatialStore(state_root)

    with pytest.raises(SpatialStoreError, match="ArrayRef"):
        store.put_snapshot(snapshot)

    assert store.list_graphs() == []


def test_store_rejects_cross_graph_or_missing_references(tmp_path: Path):
    store = SpatialStore(tmp_path / "state")
    store.create_graph(SpatialGraph(graph_id="graph_1", case_id="case_1"))

    with pytest.raises(SpatialStoreError, match="Unknown coordinate frame"):
        store.put_entity(
            "graph_1",
            SpatialEntity(
                entity_id="face_1",
                entity_kind=SpatialEntityKind.mesh_face,
                embedding_dimension=3,
                coordinate_frame_id="frame_missing",
            ),
        )

    with pytest.raises(SpatialStoreError, match="Unknown spatial entity"):
        store.put_relation(
            "graph_1",
            SpatialRelation(
                relation_id="rel_missing",
                relation_kind=SpatialRelationKind.maps_to,
                source_entity_id="missing_a",
                target_entity_id="missing_b",
            ),
        )


def test_parent_cycle_is_rejected_on_incremental_updates(tmp_path: Path):
    store = SpatialStore(tmp_path / "state")
    store.create_graph(SpatialGraph(graph_id="graph_frames", case_id="case_frames"))
    root = world_frame()
    child = CoordinateFrame(
        frame_id="frame_child",
        name="Child",
        dimension=3,
        origin=(0.0, 0.0, 0.0),
        basis=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        parent_frame_id=root.frame_id,
        transform_to_parent=(
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
        evidence_status=SpatialEvidenceStatus.derived,
    )
    store.put_frame("graph_frames", root)
    store.put_frame("graph_frames", child)

    cyclic_root = root.model_copy(
        update={
            "parent_frame_id": child.frame_id,
            "transform_to_parent": (
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            ),
        }
    )
    with pytest.raises(SpatialStoreError, match="parent cycle"):
        store.put_frame("graph_frames", cyclic_root)


def test_graph_reference_attaches_additively_to_reflexcase_metadata(tmp_path: Path):
    state_root = tmp_path / "state"
    store = SpatialStore(state_root)
    reference = store.put_snapshot(build_snapshot(state_root))
    case = ReflexCase(case_id="case_1")

    attached = attach_spatial_graph_ref(case, reference)
    attached = attach_spatial_graph_ref(attached, "graph_case_1", store=store)

    references = attached.metadata["spatial_graph_refs"]
    assert len(references) == 1
    assert references[0]["graph_id"] == "graph_case_1"
    assert references[0]["entity_count"] == 2


def test_snapshot_export_is_deterministically_sorted(tmp_path: Path):
    state_root = tmp_path / "state"
    store = SpatialStore(state_root)
    store.put_snapshot(build_snapshot(state_root))
    destination = store.export_snapshot_json("graph_case_1", tmp_path / "graph.json")
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert [item["entity_id"] for item in payload["entities"]] == [
        "mesh_face_wall",
        "surface_wall",
    ]
