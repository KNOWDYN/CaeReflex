from __future__ import annotations

from pathlib import Path

import pytest

from caereflex.arrays import ArrayService
from caereflex.spatial import (
    AxisAlignedBounds,
    CoordinateFrame,
    CoordinateHandedness,
    GATE6_FREEZE_VERSION,
    SPATIAL_QUERY_VERSION,
    SpatialArrayLink,
    SpatialArrayRole,
    SpatialBoundsMode,
    SpatialEntity,
    SpatialEntityKind,
    SpatialEvidenceStatus,
    SpatialGraph,
    SpatialGraphSnapshot,
    SpatialGraphStatus,
    SpatialQueryError,
    SpatialQueryLimits,
    SpatialQueryService,
    SpatialRelation,
    SpatialRelationKind,
    SpatialStore,
    SpatialTraversalDirection,
    validate_spatial_query_result,
    validate_spatial_snapshot,
    validate_spatial_store,
)


def _fixture(state: Path, *, registered_array: bool = True) -> tuple[SpatialStore, str, str]:
    frame = CoordinateFrame(
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
    bounds_all = AxisAlignedBounds(
        coordinate_frame_id=frame.frame_id,
        minimum=(0.0, 0.0, 0.0),
        maximum=(2.0, 2.0, 2.0),
        evidence_status=SpatialEvidenceStatus.explicit,
    )
    bounds_inner = AxisAlignedBounds(
        coordinate_frame_id=frame.frame_id,
        minimum=(0.5, 0.5, 0.5),
        maximum=(1.5, 1.5, 1.5),
        evidence_status=SpatialEvidenceStatus.explicit,
    )
    entities = [
        SpatialEntity(
            entity_id="entity_cell",
            entity_kind=SpatialEntityKind.mesh_cell,
            name="fluid cell block",
            topological_dimension=3,
            embedding_dimension=3,
            coordinate_frame_id=frame.frame_id,
            bounds=bounds_inner,
            evidence_status=SpatialEvidenceStatus.explicit,
            metadata={"count": 1},
        ),
        SpatialEntity(
            entity_id="entity_dataset",
            entity_kind=SpatialEntityKind.dataset_block,
            name="result dataset",
            topological_dimension=3,
            embedding_dimension=3,
            coordinate_frame_id=frame.frame_id,
            bounds=bounds_all,
            evidence_status=SpatialEvidenceStatus.explicit,
        ),
        SpatialEntity(
            entity_id="entity_nodes",
            entity_kind=SpatialEntityKind.mesh_node,
            name="mesh nodes",
            embedding_dimension=3,
            coordinate_frame_id=frame.frame_id,
            bounds=bounds_all,
            evidence_status=SpatialEvidenceStatus.explicit,
            metadata={"count": 8},
        ),
        SpatialEntity(
            entity_id="entity_patch",
            entity_kind=SpatialEntityKind.patch,
            name="walls",
            topological_dimension=2,
            embedding_dimension=3,
            coordinate_frame_id=frame.frame_id,
            bounds=bounds_all,
            evidence_status=SpatialEvidenceStatus.explicit,
            metadata={"native_type": "wall"},
        ),
    ]
    relations = [
        SpatialRelation(
            relation_id="relation_contains_cell",
            relation_kind=SpatialRelationKind.contains,
            source_entity_id="entity_dataset",
            target_entity_id="entity_cell",
            evidence_status=SpatialEvidenceStatus.explicit,
        ),
        SpatialRelation(
            relation_id="relation_contains_nodes",
            relation_kind=SpatialRelationKind.contains,
            source_entity_id="entity_dataset",
            target_entity_id="entity_nodes",
            evidence_status=SpatialEvidenceStatus.explicit,
        ),
        SpatialRelation(
            relation_id="relation_contains_patch",
            relation_kind=SpatialRelationKind.contains,
            source_entity_id="entity_dataset",
            target_entity_id="entity_patch",
            evidence_status=SpatialEvidenceStatus.explicit,
        ),
    ]
    arrays = ArrayService(state)
    ref = arrays.register_numeric(
        [0.0, 0.0, 0.0, 2.0, 2.0, 2.0],
        dtype="float64",
        shape=(2, 3),
        source_asset_id="asset_fixture",
        source_path="fixture.vtu",
        association="point",
        component_names=["x", "y", "z"],
        coordinate_frame_ref=frame.frame_id,
        backend="vtk.native",
        backend_version="1.0.0",
        metadata={"role": "mesh_points"},
    )
    link = SpatialArrayLink.from_array_ref(
        ref,
        link_id="link_coordinates",
        role=SpatialArrayRole.coordinates,
        owner_entity_id="entity_nodes",
        coordinate_frame_id=frame.frame_id,
        evidence_status=SpatialEvidenceStatus.explicit,
    )
    graph = SpatialGraph(
        graph_id="graph_gate6c_fixture",
        case_id="case_gate6c",
        name="Gate 6C fixture",
        default_coordinate_frame_id=frame.frame_id,
        status=SpatialGraphStatus.complete,
        metadata={
            "mapping_version": "caereflex.spatial-mapping/1.0",
            "source_backend": "vtk.native",
            "cross_format_equivalence_asserted": False,
        },
    )
    snapshot = SpatialGraphSnapshot(
        graph=graph,
        coordinate_frames=[frame],
        entities=entities,
        relations=relations,
        array_links=[link],
    )
    store = SpatialStore(state)
    store.put_snapshot(
        snapshot,
        replace=True,
        require_registered_arrays=registered_array,
    )
    return store, graph.graph_id, ref.array_id


def test_entity_relation_frame_and_array_queries_are_bounded_and_deterministic(tmp_path: Path) -> None:
    _, graph_id, array_id = _fixture(tmp_path / "state")
    service = SpatialQueryService(
        tmp_path / "state",
        limits=SpatialQueryLimits(max_results=10, max_scan_rows=100),
    )

    first = service.query_entities(
        graph_id,
        entity_kinds=[SpatialEntityKind.mesh_cell, SpatialEntityKind.mesh_node],
        limit=10,
    )
    second = service.query_entities(
        graph_id,
        entity_kinds=[SpatialEntityKind.mesh_node, SpatialEntityKind.mesh_cell],
        limit=10,
    )
    assert first.model_dump_json() == second.model_dump_json()
    assert [item.entity_id for item in first.entities] == ["entity_cell", "entity_nodes"]
    assert first.query_version == SPATIAL_QUERY_VERSION

    incoming = service.query_relations(
        graph_id,
        entity_id="entity_cell",
        direction=SpatialTraversalDirection.incoming,
    )
    assert [item.source_entity_id for item in incoming.relations] == ["entity_dataset"]
    assert incoming.metadata["inference_performed"] is False

    frames = service.query_frames(graph_id)
    assert [item.frame_id for item in frames.frames] == ["frame_world"]

    links = service.query_array_links(
        graph_id,
        owner_entity_id="entity_nodes",
        roles=[SpatialArrayRole.coordinates],
    )
    assert [item.array_id for item in links.array_links] == [array_id]
    assert links.metadata["heavy_arrays_materialized"] is False
    assert "values" not in links.model_dump_json()


def test_bounds_queries_require_one_named_frame_and_do_not_transform(tmp_path: Path) -> None:
    _, graph_id, _ = _fixture(tmp_path / "state")
    service = SpatialQueryService(tmp_path / "state")

    intersects = service.query_bounds(
        graph_id,
        coordinate_frame_id="frame_world",
        minimum=(1.25, 1.25, 1.25),
        maximum=(1.75, 1.75, 1.75),
        mode=SpatialBoundsMode.intersects,
    )
    assert {item.entity_id for item in intersects.entities} == {
        "entity_cell",
        "entity_dataset",
        "entity_nodes",
        "entity_patch",
    }
    assert intersects.metadata["coordinate_transforms_applied"] is False
    assert intersects.metadata["cross_frame_comparison"] is False

    within = service.query_bounds(
        graph_id,
        coordinate_frame_id="frame_world",
        minimum=(0.25, 0.25, 0.25),
        maximum=(1.75, 1.75, 1.75),
        mode=SpatialBoundsMode.within,
    )
    assert [item.entity_id for item in within.entities] == ["entity_cell"]

    with pytest.raises(SpatialQueryError, match="Unknown coordinate frame"):
        service.query_bounds(
            graph_id,
            coordinate_frame_id="frame_other",
            minimum=(0.0, 0.0, 0.0),
            maximum=(1.0, 1.0, 1.0),
        )


def test_neighbour_traversal_uses_recorded_relations_only(tmp_path: Path) -> None:
    _, graph_id, _ = _fixture(tmp_path / "state")
    service = SpatialQueryService(
        tmp_path / "state",
        limits=SpatialQueryLimits(max_results=10, max_depth=4),
    )
    result = service.neighbours(
        graph_id,
        "entity_dataset",
        relation_kinds=[SpatialRelationKind.contains],
        direction=SpatialTraversalDirection.outgoing,
        max_depth=2,
    )
    assert [item.entity_id for item in result.entities] == [
        "entity_cell",
        "entity_nodes",
        "entity_patch",
    ]
    assert result.metadata["recorded_relations_only"] is True
    assert result.metadata["adjacency_inferred"] is False
    assert all(depth == 1 for depth in result.metadata["depth_by_entity"].values())

    with pytest.raises(SpatialQueryError, match="exceeds the configured maximum"):
        service.neighbours(graph_id, "entity_dataset", max_depth=5)


def test_result_limits_and_pagination_fail_closed(tmp_path: Path) -> None:
    _, graph_id, _ = _fixture(tmp_path / "state")
    service = SpatialQueryService(
        tmp_path / "state",
        limits=SpatialQueryLimits(max_results=2, max_scan_rows=100),
    )
    first = service.query_entities(graph_id, limit=2)
    assert len(first.entities) == 2
    assert first.truncated is True
    assert first.next_offset == 2
    second = service.query_entities(graph_id, limit=2, offset=2)
    assert len(second.entities) == 2
    assert {item.entity_id for item in first.entities}.isdisjoint(
        {item.entity_id for item in second.entities}
    )

    with pytest.raises(SpatialQueryError, match="exceeds the configured maximum"):
        service.query_entities(graph_id, limit=3)
    with pytest.raises(SpatialQueryError, match="Unknown spatial graph"):
        service.describe_graph("graph_missing")


def test_gate6_acceptance_freeze_validates_store_and_query_contract(tmp_path: Path) -> None:
    store, graph_id, _ = _fixture(tmp_path / "state")
    first = validate_spatial_store(tmp_path / "state", graph_id)
    second = validate_spatial_store(tmp_path / "state", graph_id)

    assert first.accepted is True
    assert first.freeze_version == GATE6_FREEZE_VERSION
    assert first.canonical_sha256 == second.canonical_sha256
    assert first.checks["sqlite_foreign_keys"] is True
    assert first.checks["bounded_query_surface"] is True
    assert store.validate_integrity() == []

    query = SpatialQueryService(tmp_path / "state").query_entities(graph_id, limit=2)
    assert validate_spatial_query_result(query) == []


def test_freeze_rejects_cross_format_equivalence_and_unregistered_arrays(tmp_path: Path) -> None:
    store, graph_id, _ = _fixture(tmp_path / "state")
    snapshot = store.snapshot(graph_id)
    snapshot.graph.metadata["cross_format_equivalence_asserted"] = True
    report = validate_spatial_snapshot(snapshot)
    assert report.accepted is False
    assert any("cross-format" in issue.message for issue in report.errors)

    missing_state = tmp_path / "missing-array-state"
    source_store, source_graph_id, _ = _fixture(tmp_path / "source")
    missing_snapshot = source_store.snapshot(source_graph_id)
    SpatialStore(missing_state).put_snapshot(
        missing_snapshot,
        replace=True,
        require_registered_arrays=False,
    )
    missing_report = validate_spatial_store(missing_state, source_graph_id)
    assert missing_report.accepted is False
    assert any("absent from the shared registry" in issue.message for issue in missing_report.errors)
