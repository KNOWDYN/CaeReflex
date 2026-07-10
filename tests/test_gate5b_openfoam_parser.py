from pathlib import Path

import pytest

from caereflex.openfoam_native.parser import (
    OpenFOAMNativeError,
    OpenFOAMUnsupportedError,
    build_mesh,
    decode_foam_text,
    parse_boundary,
    parse_faces,
    parse_field,
    parse_label_list,
    parse_points,
    unsafe_constructs,
)

FIXTURE = Path("examples/openfoam_cavity_native")


def _read(relative: str) -> str:
    return (FIXTURE / relative).read_text(encoding="utf-8")


def test_native_ascii_mesh_parsers_reconstruct_single_cell():
    points = parse_points(_read("constant/polyMesh/points"))
    faces = parse_faces(_read("constant/polyMesh/faces"))
    owner = parse_label_list(_read("constant/polyMesh/owner"), "owner")
    neighbour = parse_label_list(_read("constant/polyMesh/neighbour"), "neighbour")
    patches = parse_boundary(_read("constant/polyMesh/boundary"))
    mesh = build_mesh(points, faces, owner, neighbour, patches)

    assert len(mesh.points) == 8
    assert len(mesh.faces) == 6
    assert len(mesh.owner) == 6
    assert mesh.neighbour == []
    assert mesh.cell_count == 1
    assert mesh.bounds_min == (0.0, 0.0, 0.0)
    assert mesh.bounds_max == (1.0, 1.0, 1.0)
    assert [patch["name"] for patch in mesh.patches] == ["movingWall", "fixedWalls", "frontAndBack"]
    assert mesh.warnings == []


def test_native_field_parser_supports_uniform_and_nonuniform_values():
    initial_u = parse_field(_read("0/U"), fallback_name="U")
    time_u = parse_field(_read("1/U"), fallback_name="U")
    time_p = parse_field(_read("1/p"), fallback_name="p")

    assert initial_u.field_class == "volVectorField"
    assert initial_u.association == "cell"
    assert initial_u.components == 3
    assert initial_u.internal_mode == "uniform"
    assert initial_u.internal_values == [0, 0, 0]
    assert len(initial_u.boundary) == 3

    assert time_u.internal_mode == "nonuniform"
    assert time_u.internal_count == 1
    assert time_u.internal_values == [0.5, 0, 0]
    assert time_p.components == 1
    assert time_p.internal_values == [0.25]


def test_unsafe_constructs_are_detected_but_not_evaluated():
    text = """
    #include \"otherDict\"
    value $internalField;
    patch { type codedFixedValue; code #{ malicious(); #}; }
    libs (\"libSomething.so\");
    """
    found = unsafe_constructs(text)
    assert {item["code"] for item in found} >= {
        "include",
        "substitution",
        "coded_boundary",
        "dynamic_library",
    }


def test_binary_openfoam_payload_is_explicitly_rejected():
    payload = b"FoamFile { version 2.0; format binary; class vectorField; object points; }\n\x00\x01"
    with pytest.raises(OpenFOAMUnsupportedError, match="native ASCII"):
        decode_foam_text(payload, "constant/polyMesh/points", max_decompressed_bytes=1024)


def test_topology_validation_rejects_out_of_range_point_labels():
    with pytest.raises(OpenFOAMNativeError, match="outside"):
        build_mesh(
            [(0.0, 0.0, 0.0)],
            [[0, 1, 0]],
            [0],
            [],
            [{"name": "wall", "type": "wall", "n_faces": 1, "start_face": 0, "metadata": {}}],
        )
