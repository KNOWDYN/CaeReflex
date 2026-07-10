"""Optional PyVista/VTK dataset reader used by ``vtk.native``.

The module is kept separate so native import failures are recorded accurately rather
than being confused with an absent dependency. VTK can reserve substantial virtual
address space while importing, so callers must provide an execution memory budget
appropriate to their platform.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from caereflex.execution.context import ExecutionContext
from caereflex.execution.vtk_common import VTKNativeError, _array_record, _finite, _register_dataset


def _to_list(values: Any) -> list[Any]:
    if hasattr(values, "ravel"):
        values = values.ravel()
    if hasattr(values, "tolist"):
        values = values.tolist()
    if isinstance(values, list):
        result: list[Any] = []
        for item in values:
            result.extend(item if isinstance(item, list) else [item])
        return result
    return list(values)


def _dtype_name(values: Any) -> str:
    dtype = getattr(values, "dtype", None)
    kind = getattr(dtype, "kind", None)
    itemsize = int(getattr(dtype, "itemsize", 8) or 8)
    if kind == "b":
        return "bool"
    if kind == "u":
        return f"uint{itemsize * 8}"
    if kind == "i":
        return f"int{itemsize * 8}"
    return "float32" if itemsize <= 4 else "float64"


def _fields(container: Any, association: str) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for name in getattr(container, "keys", lambda: [])():
        values = container[name]
        shape = tuple(int(item) for item in getattr(values, "shape", (len(values),)))
        tuples = shape[0] if shape else 1
        components = shape[1] if len(shape) > 1 else 1
        flattened = _to_list(values)
        if not all(isinstance(value, (bool, int, float)) for value in flattened):
            continue
        fields.append(
            _array_record(
                name=str(name),
                association=association,
                components=components,
                tuples=tuples,
                dtype=_dtype_name(values),
                values=_finite(flattened),
                role="optional_reader_data",
            )
        )
    return fields


def pyvista_summary(
    staged_path: Path,
    context: ExecutionContext,
    source_path: str,
    asset_id: str,
    backend_version: str,
) -> dict[str, Any]:
    """Decode one staged dataset through PyVista without launching ParaView."""

    try:
        import pyvista as pv  # type: ignore
    except ImportError as exc:
        raise ModuleNotFoundError(f"PyVista/VTK import is unavailable: {exc}") from exc
    except Exception as exc:
        raise VTKNativeError(
            f"PyVista/VTK import failed under the worker execution policy: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    dataset = pv.read(str(staged_path))
    if hasattr(dataset, "n_blocks"):
        raise VTKNativeError("PyVista multiblock results remain collection inventories in Gate 5D.")

    points_object = getattr(dataset, "points", [])
    points_values = _to_list(points_object)
    point_count = int(getattr(dataset, "n_points", len(points_values) // 3))
    cell_count = int(getattr(dataset, "n_cells", 0))
    cell_types = [int(value) for value in _to_list(getattr(dataset, "celltypes", []))]

    connectivity: list[int] = []
    offsets: list[int] = []
    if hasattr(dataset, "cell_connectivity") and hasattr(dataset, "offset"):
        connectivity = [int(value) for value in _to_list(dataset.cell_connectivity)]
        raw_offsets = [int(value) for value in _to_list(dataset.offset)]
        offsets = raw_offsets[1:] if len(raw_offsets) == cell_count + 1 and raw_offsets[:1] == [0] else raw_offsets
    elif hasattr(dataset, "cells"):
        raw = [int(value) for value in _to_list(dataset.cells)]
        cursor = 0
        while cursor < len(raw):
            count = raw[cursor]
            cursor += 1
            if count < 0 or cursor + count > len(raw):
                raise VTKNativeError("PyVista returned malformed legacy-style cell connectivity.")
            connectivity.extend(raw[cursor:cursor + count])
            cursor += count
            offsets.append(len(connectivity))
        if cursor != len(raw):
            raise VTKNativeError("PyVista cell connectivity contains trailing values.")

    raw_bounds = list(dataset.bounds)
    if len(raw_bounds) != 6:
        raise VTKNativeError("PyVista returned an invalid bounds tuple.")

    parsed = {
        "dataset_type": type(dataset).__name__,
        "points": _finite(points_values),
        "points_dtype": _dtype_name(points_object),
        "point_count": point_count,
        "connectivity": connectivity,
        "offsets": offsets,
        "cell_types": cell_types,
        "cell_count": cell_count,
        "fields": [
            *_fields(dataset.point_data, "point"),
            *_fields(dataset.cell_data, "cell"),
            *_fields(dataset.field_data, "field"),
        ],
        "bounds": [
            [float(raw_bounds[0]), float(raw_bounds[1])],
            [float(raw_bounds[2]), float(raw_bounds[3])],
            [float(raw_bounds[4]), float(raw_bounds[5])],
        ],
        "encoding": "optional-pyvista",
        "byte_order": "native",
    }
    return _register_dataset(
        parsed,
        context,
        source_path=source_path,
        asset_id=asset_id,
        backend_version=backend_version,
        reader="vtk.pyvista",
    )


__all__ = ["pyvista_summary"]
