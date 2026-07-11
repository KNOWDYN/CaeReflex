import math

import pytest
from pydantic import ValidationError

from caereflex.spatial import (
    AxisAlignedBounds,
    CoordinateFrame,
    CoordinateHandedness,
    SpatialArrayLink,
    SpatialArrayRole,
    SpatialEntity,
    SpatialEntityKind,
    SpatialEvidenceStatus,
    SpatialGraph,
    SpatialGraphSnapshot,
    SpatialRelation,
    SpatialRelationKind,
)


def explicit_world_frame() -> CoordinateFrame:
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


def test_unresolved_frame_does_not_assume_origin_axes_handedness_or_units():
    frame = CoordinateFrame(
        frame_id="frame_unknown",
        name="Unresolved source frame",
        dimension=3,
    )

    assert frame.origin is None
    assert frame.basis is None
    assert frame.handedness == "unknown"
    assert frame.length_unit is None
    assert frame.length_unit_status == "unresolved"
    assert frame.evidence_status == "unresolved"


def test_resolved_frame_requires_origin_and_basis():
    with pytest.raises(ValidationError, match="origin and basis"):
        CoordinateFrame(
            frame_id="frame_invalid",
            name="Invalid",
            dimension=3,
            evidence_status=SpatialEvidenceStatus.explicit,
        )


def test_handedness_and_linear_independence_are_checked():
    frame = explicit_world_frame()
    assert frame.handedness == "right"

    with pytest.raises(ValidationError, match="positive basis determinant"):
        CoordinateFrame(
            frame_id="frame_wrong_handedness",
            name="Wrong",
            dimension=3,
            origin=(0.0, 0.0, 0.0),
            basis=((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
            handedness=CoordinateHandedness.right,
            evidence_status=SpatialEvidenceStatus.explicit,
        )

    with pytest.raises(ValidationError, match="linearly independent"):
        CoordinateFrame(
            frame_id="frame_singular",
            name="Singular",
            dimension=2,
            origin=(0.0, 0.0, 0.0),
            basis=((1.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
            evidence_status=SpatialEvidenceStatus.explicit,
        )


def test_two_dimensional_frame_does_not_claim_handedness():
    with pytest.raises(ValidationError, match="only declared for complete 3D"):
        CoordinateFrame(
            frame_id="frame_2d",
            name="Plane",
            dimension=2,
            origin=(0.0, 0.0, 0.0),
            basis=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            handedness=CoordinateHandedness.right,
            evidence_status=SpatialEvidenceStatus.explicit,
        )


def test_length_unit_requires_an_evidence_state():
    with pytest.raises(ValidationError, match="unresolved unit status"):
        CoordinateFrame(
            frame_id="frame_unit_invalid",
            name="Invalid unit evidence",
            dimension=3,
            length_unit="mm",
        )


def test_affine_parent_transform_is_required_for_resolved_child_frames():
    with pytest.raises(ValidationError, match="transform_to_parent"):
        CoordinateFrame(
            frame_id="frame_child",
            name="Child",
            dimension=3,
            origin=(0.0, 0.0, 0.0),
            basis=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            parent_frame_id="frame_world",
            evidence_status=SpatialEvidenceStatus.derived,
        )


def test_geometry_and_mesh_entities_remain_distinct():
    surface = SpatialEntity(
        entity_id="surface_wall",
        entity_kind=SpatialEntityKind.geometry_surface,
        embedding_dimension=3,
    )
    face = SpatialEntity(
        entity_id="mesh_face_1",
        entity_kind=SpatialEntityKind.mesh_face,
        embedding_dimension=3,
    )

    assert surface.domain == "geometry"
    assert face.domain == "mesh"
    assert surface.topological_dimension == 2
    assert face.topological_dimension == 2

    with pytest.raises(ValidationError, match="requires topological_dimension=2"):
        SpatialEntity(
            entity_id="bad_surface",
            entity_kind=SpatialEntityKind.geometry_surface,
            topological_dimension=3,
            embedding_dimension=3,
        )


def test_bounds_are_compact_and_frame_explicit():
    bounds = AxisAlignedBounds(
        coordinate_frame_id="frame_world",
        minimum=(0.0, 0.0, 0.0),
        maximum=(1.0, 2.0, 3.0),
        evidence_status=SpatialEvidenceStatus.explicit,
    )
    entity = SpatialEntity(
        entity_id="volume_1",
        entity_kind=SpatialEntityKind.geometry_volume,
        embedding_dimension=3,
        bounds=bounds,
    )
    assert entity.coordinate_frame_id == "frame_world"

    with pytest.raises(ValidationError, match="minimum bounds"):
        AxisAlignedBounds(
            coordinate_frame_id="frame_world",
            minimum=(2.0, 0.0, 0.0),
            maximum=(1.0, 1.0, 1.0),
        )


def test_relation_direction_is_canonical():
    SpatialRelation(
        relation_id="rel_discretises",
        relation_kind=SpatialRelationKind.discretises,
        source_entity_id="mesh_face_1",
        target_entity_id="surface_wall",
    )
    SpatialRelation(
        relation_id="rel_adjacent",
        relation_kind=SpatialRelationKind.adjacent_to,
        source_entity_id="mesh_face_1",
        target_entity_id="mesh_face_2",
        directed=False,
    )

    with pytest.raises(ValidationError, match="must be undirected"):
        SpatialRelation(
            relation_id="bad_adjacent",
            relation_kind=SpatialRelationKind.adjacent_to,
            source_entity_id="a",
            target_entity_id="b",
        )

    with pytest.raises(ValidationError, match="self-relations"):
        SpatialRelation(
            relation_id="bad_self",
            relation_kind=SpatialRelationKind.maps_to,
            source_entity_id="a",
            target_entity_id="a",
        )


def test_heavy_sequences_and_non_finite_metadata_are_rejected():
    with pytest.raises(ValidationError, match="use ArrayRef"):
        SpatialEntity(
            entity_id="heavy",
            entity_kind=SpatialEntityKind.region,
            metadata={"coordinates": list(range(300))},
        )

    with pytest.raises(ValidationError, match="non-finite"):
        SpatialEntity(
            entity_id="nan",
            entity_kind=SpatialEntityKind.region,
            metadata={"score": math.nan},
        )


def test_array_link_requires_one_owner_and_content_addressed_uri():
    link = SpatialArrayLink(
        link_id="link_coordinates",
        array_id="array_coordinates",
        role=SpatialArrayRole.coordinates,
        owner_entity_id="mesh_nodes",
        array_uri="caereflex-artifact://sha256/" + "0" * 64,
    )
    assert link.owner_entity_id == "mesh_nodes"

    with pytest.raises(ValidationError, match="exactly one"):
        SpatialArrayLink(
            link_id="bad_owner",
            array_id="array_coordinates",
            role=SpatialArrayRole.coordinates,
        )


def test_snapshot_rejects_missing_references_and_frame_cycles():
    graph = SpatialGraph(
        graph_id="graph_missing_frame",
        case_id="case_1",
        default_coordinate_frame_id="frame_missing",
    )
    with pytest.raises(ValidationError, match="default coordinate frame"):
        SpatialGraphSnapshot(graph=graph)

    root = CoordinateFrame(frame_id="frame_a", name="A", dimension=3, parent_frame_id="frame_b")
    child = CoordinateFrame(frame_id="frame_b", name="B", dimension=3, parent_frame_id="frame_a")
    with pytest.raises(ValidationError, match="parent cycle"):
        SpatialGraphSnapshot(
            graph=SpatialGraph(graph_id="graph_cycle", case_id="case_1"),
            coordinate_frames=[root, child],
        )
