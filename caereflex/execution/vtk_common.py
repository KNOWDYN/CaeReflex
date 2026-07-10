"""Shared primitives for bounded, read-only VTK inspection."""
from __future__ import annotations

import hashlib
import math
import uuid
from collections import Counter
from typing import Any, Iterable

from caereflex.contracts import AttemptOutcome, DiagnosticEvent, ParserAttempt
from caereflex.core.provenance import utc_now_iso
from caereflex.execution.context import ExecutionContext


class VTKNativeError(RuntimeError):
    """Raised when a VTK artefact cannot be decoded safely."""


_DATASET_SUFFIXES = {".vtk", ".vtu", ".vtp", ".vti", ".vtr", ".vts"}
_PARALLEL_SUFFIXES = {".pvtu", ".pvtp", ".pvti", ".pvtr", ".pvts"}
_COLLECTION_SUFFIXES = {".pvd", ".vtm", ".vtmb"}
_VTK_SUFFIXES = _DATASET_SUFFIXES | _PARALLEL_SUFFIXES | _COLLECTION_SUFFIXES

_XML_TYPES: dict[str, tuple[str, str]] = {
    "Int8": ("int8", "b"), "UInt8": ("uint8", "B"),
    "Int16": ("int16", "h"), "UInt16": ("uint16", "H"),
    "Int32": ("int32", "i"), "UInt32": ("uint32", "I"),
    "Int64": ("int64", "q"), "UInt64": ("uint64", "Q"),
    "Float32": ("float32", "f"), "Float64": ("float64", "d"),
}
_LEGACY_DTYPES: dict[str, str] = {
    "bit": "bool", "char": "int8", "signed_char": "int8", "unsigned_char": "uint8",
    "short": "int16", "unsigned_short": "uint16", "int": "int32", "unsigned_int": "uint32",
    "long": "int64", "unsigned_long": "uint64", "long_long": "int64",
    "unsigned_long_long": "uint64", "float": "float32", "double": "float64",
}
_COMPONENT_NAMES = {
    1: [], 2: ["x", "y"], 3: ["x", "y", "z"], 4: ["x", "y", "z", "w"],
    6: ["xx", "xy", "xz", "yy", "yz", "zz"],
    9: ["xx", "xy", "xz", "yx", "yy", "yz", "zx", "zy", "zz"],
}
_CELL_DIMENSIONS = {
    1: 0, 2: 0, 3: 1, 4: 1, 21: 1, 35: 1,
    5: 2, 6: 2, 7: 2, 8: 2, 9: 2, 22: 2, 23: 2, 28: 2, 29: 2, 30: 2, 31: 2, 32: 2, 33: 2, 34: 2,
    10: 3, 11: 3, 12: 3, 13: 3, 14: 3, 15: 3, 16: 3, 24: 3, 25: 3, 26: 3, 27: 3, 42: 3,
}
_CELL_NAMES = {
    1: "vertex", 2: "poly_vertex", 3: "line", 4: "poly_line", 5: "triangle", 6: "triangle_strip",
    7: "polygon", 8: "pixel", 9: "quad", 10: "tetra", 11: "voxel", 12: "hexahedron",
    13: "wedge", 14: "pyramid", 15: "pentagonal_prism", 16: "hexagonal_prism", 21: "quadratic_edge",
    22: "quadratic_triangle", 23: "quadratic_quad", 24: "quadratic_tetra", 25: "quadratic_hexahedron",
    26: "quadratic_wedge", 27: "quadratic_pyramid", 28: "biquadratic_quad", 29: "triquadratic_hexahedron",
    30: "quadratic_linear_quad", 31: "quadratic_linear_wedge", 32: "biquadratic_quadratic_wedge",
    33: "biquadratic_quadratic_hexahedron", 34: "biquadratic_triangle", 35: "cubic_line", 42: "polyhedron",
}
_MESHIO_CELL_TO_VTK = {
    "vertex": 1, "line": 3, "line3": 21, "triangle": 5, "triangle6": 22,
    "quad": 9, "quad8": 23, "quad9": 28, "tetra": 10, "tetra10": 24,
    "hexahedron": 12, "hexahedron20": 25, "hexahedron27": 29,
    "wedge": 13, "wedge15": 26, "wedge18": 32, "pyramid": 14,
    "pyramid13": 27, "pyramid14": 27,
}


def _attempt(
    context: ExecutionContext,
    *,
    stage: str,
    backend_id: str,
    outcome: AttemptOutcome,
    started_at: str,
    error: Exception | None = None,
    fallback_to: str | None = None,
    information_lost: list[str] | None = None,
    diagnostics: list[DiagnosticEvent] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    context.record_attempt(
        ParserAttempt(
            attempt_id=f"attempt_{uuid.uuid4().hex[:20]}",
            stage=stage,
            backend_id=backend_id,
            backend_version="1.0.0",
            outcome=outcome,
            started_at=started_at,
            completed_at=utc_now_iso(),
            exception_type=type(error).__name__ if error else None,
            exception_message=str(error) if error else None,
            fallback_to=fallback_to,
            information_lost=information_lost or [],
            diagnostics=diagnostics or [],
            metadata=metadata or {},
        )
    )


def _finite(values: Iterable[int | float]) -> list[int | float]:
    output = list(values)
    if any(isinstance(value, float) and not math.isfinite(value) for value in output):
        raise VTKNativeError("Non-finite VTK values are not accepted by the bounded core reader.")
    return output


def _bounds(points: list[int | float]) -> list[list[float]] | None:
    if not points:
        return None
    if len(points) % 3:
        raise VTKNativeError("Point-coordinate payload is not divisible into three components.")
    axes = [[float(points[index]) for index in range(axis, len(points), 3)] for axis in range(3)]
    return [[min(axis), max(axis)] for axis in axes]


def _component_names(count: int) -> list[str]:
    return list(_COMPONENT_NAMES.get(count, [f"c{index}" for index in range(count)])) if count > 1 else []


def _normalise_dtype(dtype: str) -> str:
    key = dtype.strip().lower()
    if key in _LEGACY_DTYPES:
        return _LEGACY_DTYPES[key]
    for vtk_name, (name, _) in _XML_TYPES.items():
        if key == vtk_name.lower():
            return name
    raise VTKNativeError(f"Unsupported VTK numeric type: {dtype}")


def _convert_token(token: str, dtype: str) -> int | float | bool:
    if dtype == "bool":
        return bool(int(token))
    if dtype.startswith("float"):
        value = float(token)
        if not math.isfinite(value):
            raise VTKNativeError("Non-finite VTK numerical value detected.")
        return value
    return int(token, 0)


def _register_array(
    context: ExecutionContext,
    values: Iterable[int | float | bool],
    *,
    dtype: str,
    shape: tuple[int, ...],
    source_path: str,
    asset_id: str,
    association: str,
    name: str,
    backend_version: str,
    time_index: str | float | int | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    components = shape[-1] if len(shape) > 1 else 1
    ref = context.register_numeric_array(
        values,
        dtype=dtype,
        shape=shape,
        source_asset_id=asset_id,
        source_path=source_path,
        association=association,
        component_names=_component_names(components),
        coordinate_frame_ref="vtk_dataset_frame" if name == "points" else None,
        time_index=time_index,
        backend_version=backend_version,
        metadata={"name": name, **(metadata or {})},
    )
    return ref.array_id


def _fingerprint(payload: bytes, source_path: str, suffix: str) -> dict[str, Any]:
    return {
        "source_path": source_path,
        "kind": "vtk_fingerprint",
        "status": "fingerprinted",
        "suffix": suffix,
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "decoded": False,
    }


def _validate_connectivity(point_count: int | None, offsets: list[int], connectivity: list[int]) -> None:
    if offsets:
        previous = 0
        for offset in offsets:
            if offset < previous or offset > len(connectivity):
                raise VTKNativeError("VTK cell offsets are not monotonically valid.")
            previous = offset
        if offsets[-1] != len(connectivity):
            raise VTKNativeError("Final VTK cell offset does not match connectivity length.")
    if point_count is not None and any(value < 0 or value >= point_count for value in connectivity):
        raise VTKNativeError("VTK connectivity references a point outside the declared point range.")


def _cell_summary(cell_types: list[int]) -> list[dict[str, Any]]:
    counts = Counter(cell_types)
    return [
        {
            "vtk_type": cell_type,
            "name": _CELL_NAMES.get(cell_type, f"vtk_type_{cell_type}"),
            "dimension": _CELL_DIMENSIONS.get(cell_type),
            "count": count,
        }
        for cell_type, count in sorted(counts.items())
    ]


def _dataset_dimension(cell_types: list[int], extent: list[int] | None = None) -> int | None:
    dimensions = [_CELL_DIMENSIONS[item] for item in cell_types if item in _CELL_DIMENSIONS]
    if dimensions:
        return max(dimensions)
    if extent and len(extent) == 6:
        return sum(1 for axis in range(3) if extent[axis * 2 + 1] > extent[axis * 2])
    return None


def _array_record(
    *, name: str, association: str, components: int, tuples: int, dtype: str,
    values: list[int | float | bool], role: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "association": association,
        "components": components,
        "tuples": tuples,
        "dtype": dtype,
        "values": values,
        "role": role,
    }


def _register_dataset(
    parsed: dict[str, Any],
    context: ExecutionContext,
    *, source_path: str, asset_id: str, backend_version: str, reader: str,
) -> dict[str, Any]:
    arrays: dict[str, Any] = {}
    points = parsed.get("points") or []
    point_count = parsed.get("point_count")
    if points:
        point_count = len(points) // 3
        arrays["points_array_id"] = _register_array(
            context, points, dtype=str(parsed.get("points_dtype", "float64")), shape=(point_count, 3),
            source_path=source_path, asset_id=asset_id, association="point", name="points",
            backend_version=backend_version,
            metadata={"role": "mesh_points", "reader": reader, "length_units": "unresolved"},
        )
    connectivity = parsed.get("connectivity") or []
    offsets = parsed.get("offsets") or []
    cell_types = parsed.get("cell_types") or []
    _validate_connectivity(point_count, offsets, connectivity)
    cell_count = parsed.get("cell_count")
    if offsets:
        cell_count = len(offsets)
        arrays["cell_offsets_array_id"] = _register_array(
            context, offsets, dtype="int64", shape=(len(offsets),), source_path=source_path, asset_id=asset_id,
            association="cell", name="cell_offsets", backend_version=backend_version,
            metadata={"role": "ragged_cell_offsets", "reader": reader},
        )
    if connectivity:
        arrays["cell_connectivity_array_id"] = _register_array(
            context, connectivity, dtype="int64", shape=(len(connectivity),), source_path=source_path,
            asset_id=asset_id, association="cell", name="cell_connectivity", backend_version=backend_version,
            metadata={"role": "ragged_cell_connectivity", "reader": reader},
        )
    if cell_types:
        if cell_count is not None and len(cell_types) != int(cell_count):
            raise VTKNativeError("VTK cell-type count does not match the declared cell count.")
        arrays["cell_types_array_id"] = _register_array(
            context, cell_types, dtype="uint8" if max(cell_types, default=0) <= 255 else "int32",
            shape=(len(cell_types),), source_path=source_path, asset_id=asset_id, association="cell",
            name="cell_types", backend_version=backend_version,
            metadata={"role": "vtk_cell_types", "reader": reader},
        )
    field_summaries: list[dict[str, Any]] = []
    for field in parsed.get("fields", []):
        values = field.get("values") or []
        components = int(field.get("components", 1))
        tuples = int(field.get("tuples", 0))
        if tuples * components != len(values):
            raise VTKNativeError(f"Field {field.get('name')} shape does not match its decoded value count.")
        shape = (tuples,) if components == 1 else (tuples, components)
        array_id = _register_array(
            context, values, dtype=str(field.get("dtype", "float64")), shape=shape,
            source_path=source_path, asset_id=asset_id,
            association=str(field.get("association", "field")),
            name=str(field.get("name") or "unnamed"), backend_version=backend_version,
            time_index=field.get("time_index"),
            metadata={"role": field.get("role") or "vtk_data_array", "reader": reader, "units": "unresolved"},
        )
        field_summaries.append({
            "name": field.get("name"), "association": field.get("association"),
            "components": components, "tuples": tuples, "dtype": field.get("dtype"),
            "array_id": array_id, "role": field.get("role"), "units": "unresolved",
        })
    axes: dict[str, str] = {}
    for axis, values in (parsed.get("coordinate_axes") or {}).items():
        if values:
            axes[axis] = _register_array(
                context, values, dtype="float64", shape=(len(values),), source_path=source_path,
                asset_id=asset_id, association="coordinate", name=f"{axis}_coordinates",
                backend_version=backend_version,
                metadata={"role": "rectilinear_coordinate_axis", "reader": reader, "length_units": "unresolved"},
            )
    if axes:
        arrays["coordinate_axis_array_ids"] = axes
    return {
        "source_path": source_path,
        "kind": "vtk_dataset",
        "status": "decoded",
        "reader": reader,
        "dataset_type": parsed.get("dataset_type"),
        "point_count": point_count,
        "cell_count": cell_count,
        "bounds": parsed.get("bounds") or _bounds(points),
        "dimension": parsed.get("dimension") if parsed.get("dimension") is not None else _dataset_dimension(cell_types, parsed.get("extent")),
        "cell_types": _cell_summary(cell_types),
        "fields": field_summaries,
        "arrays": arrays,
        "extent": parsed.get("extent"),
        "origin": parsed.get("origin"),
        "spacing": parsed.get("spacing"),
        "direction": parsed.get("direction"),
        "coordinate_units": "unresolved",
        "byte_order": parsed.get("byte_order"),
        "encoding": parsed.get("encoding"),
    }


__all__ = [
    "VTKNativeError", "_DATASET_SUFFIXES", "_PARALLEL_SUFFIXES", "_COLLECTION_SUFFIXES", "_VTK_SUFFIXES",
    "_XML_TYPES", "_MESHIO_CELL_TO_VTK", "_attempt", "_finite", "_bounds", "_component_names",
    "_normalise_dtype", "_convert_token", "_register_array", "_fingerprint", "_dataset_dimension",
    "_array_record", "_register_dataset",
]
