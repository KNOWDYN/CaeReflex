"""Read-only native OpenFOAM ASCII inspection."""
from .backend import OpenFOAMNativeBackend
from .parser import (
    FieldData,
    MeshData,
    OpenFOAMNativeError,
    OpenFOAMUnsupportedError,
    build_mesh,
    parse_boundary,
    parse_faces,
    parse_field,
    parse_label_list,
    parse_points,
)

__all__ = [
    "FieldData",
    "MeshData",
    "OpenFOAMNativeBackend",
    "OpenFOAMNativeError",
    "OpenFOAMUnsupportedError",
    "build_mesh",
    "parse_boundary",
    "parse_faces",
    "parse_field",
    "parse_label_list",
    "parse_points",
]
