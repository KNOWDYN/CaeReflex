"""Dependency-free bounded reader for legacy ASCII VTK datasets."""
from __future__ import annotations

import math
from typing import Any

from caereflex.execution.vtk_common import (
    VTKNativeError, _normalise_dtype, _convert_token, _finite, _array_record, _dataset_dimension,
)


def _legacy_numeric_lines(lines: list[str], index: int, count: int, dtype: str) -> tuple[list[int | float | bool], int]:
    values: list[int | float | bool] = []
    while len(values) < count and index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line:
            continue
        tokens = line.split()
        try:
            values.extend(_convert_token(token, dtype) for token in tokens)
        except (ValueError, OverflowError) as exc:
            raise VTKNativeError(f"Malformed legacy VTK numeric payload near line {index}.") from exc
        if len(values) > count:
            raise VTKNativeError("Legacy VTK numerical record contains more values than declared.")
    if len(values) != count:
        raise VTKNativeError(f"Legacy VTK expected {count} values but decoded {len(values)}.")
    return _finite(values), index


def _legacy_cells(lines: list[str], index: int, cell_count: int, size: int) -> tuple[list[int], list[int], int]:
    values, index = _legacy_numeric_lines(lines, index, size, "int64")
    ints = [int(item) for item in values]
    offsets: list[int] = []
    connectivity: list[int] = []
    cursor = 0
    for _ in range(cell_count):
        if cursor >= len(ints):
            raise VTKNativeError("Legacy VTK cell list ended before all cells were decoded.")
        count = ints[cursor]
        cursor += 1
        if count < 0 or cursor + count > len(ints):
            raise VTKNativeError("Legacy VTK cell connectivity count is invalid.")
        connectivity.extend(ints[cursor:cursor + count])
        cursor += count
        offsets.append(len(connectivity))
    if cursor != len(ints):
        raise VTKNativeError("Legacy VTK cell section contains undeclared connectivity values.")
    return offsets, connectivity, index


def _legacy_poly_types(section: str, offsets: list[int]) -> list[int]:
    previous = 0
    result: list[int] = []
    for offset in offsets:
        count = offset - previous
        previous = offset
        if section == "VERTICES":
            result.append(1 if count == 1 else 2)
        elif section == "LINES":
            result.append(3 if count == 2 else 4)
        elif section == "TRIANGLE_STRIPS":
            result.append(6)
        else:
            result.append(5 if count == 3 else 9 if count == 4 else 7)
    return result


def _legacy_array(
    lines: list[str], index: int, header: list[str], association: str, tuple_count: int,
) -> tuple[dict[str, Any], int]:
    keyword = header[0].upper()
    if keyword == "SCALARS":
        if len(header) < 3:
            raise VTKNativeError("Malformed SCALARS declaration.")
        name, dtype = header[1], _normalise_dtype(header[2])
        components = int(header[3]) if len(header) > 3 else 1
        if index >= len(lines) or not lines[index].strip().upper().startswith("LOOKUP_TABLE"):
            raise VTKNativeError("SCALARS declaration is missing LOOKUP_TABLE.")
        index += 1
    elif keyword in {"VECTORS", "NORMALS"}:
        if len(header) < 3:
            raise VTKNativeError(f"Malformed {keyword} declaration.")
        name, dtype, components = header[1], _normalise_dtype(header[2]), 3
    elif keyword == "TENSORS":
        if len(header) < 3:
            raise VTKNativeError("Malformed TENSORS declaration.")
        name, dtype, components = header[1], _normalise_dtype(header[2]), 9
    elif keyword == "TEXTURE_COORDINATES":
        if len(header) < 4:
            raise VTKNativeError("Malformed TEXTURE_COORDINATES declaration.")
        name, components, dtype = header[1], int(header[2]), _normalise_dtype(header[3])
    elif keyword == "COLOR_SCALARS":
        if len(header) < 3:
            raise VTKNativeError("Malformed COLOR_SCALARS declaration.")
        name, components, dtype = header[1], int(header[2]), "float32"
    else:
        raise VTKNativeError(f"Unsupported legacy VTK array declaration: {keyword}")
    values, index = _legacy_numeric_lines(lines, index, tuple_count * components, dtype)
    return _array_record(
        name=name, association=association, components=components, tuples=tuple_count,
        dtype=dtype, values=values, role=keyword.lower(),
    ), index


def parse_legacy_ascii(payload: bytes) -> dict[str, Any]:
    if b"\x00" in payload:
        raise VTKNativeError("Binary legacy VTK payload detected.")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise VTKNativeError("Legacy VTK file is not valid UTF-8 ASCII text.") from exc
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(lines) < 4 or not lines[0].lstrip().lower().startswith("# vtk datafile"):
        raise VTKNativeError("Legacy VTK signature was not found.")
    mode = lines[2].strip().upper()
    if mode != "ASCII":
        raise VTKNativeError(f"Legacy VTK {mode or 'unknown'} encoding requires an optional native reader.")
    dataset_header = lines[3].strip().split()
    if len(dataset_header) < 2 or dataset_header[0].upper() != "DATASET":
        raise VTKNativeError("Legacy VTK DATASET declaration was not found.")
    dataset_type = dataset_header[1].upper()
    parsed: dict[str, Any] = {
        "dataset_type": dataset_type,
        "points": [], "points_dtype": "float64", "connectivity": [], "offsets": [], "cell_types": [],
        "fields": [], "coordinate_axes": {}, "encoding": "legacy-ascii", "byte_order": "native",
    }
    index = 4
    association = "field"
    tuple_count = 1
    poly_sections: list[tuple[list[int], list[int], list[int]]] = []
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line:
            continue
        header = line.split()
        keyword = header[0].upper()
        if keyword == "POINTS":
            if len(header) < 3:
                raise VTKNativeError("Malformed POINTS declaration.")
            count, dtype = int(header[1]), _normalise_dtype(header[2])
            values, index = _legacy_numeric_lines(lines, index, count * 3, dtype)
            parsed["points"] = values
            parsed["points_dtype"] = dtype
            parsed["point_count"] = count
        elif keyword == "CELLS":
            if len(header) < 3:
                raise VTKNativeError("Malformed CELLS declaration.")
            count, size = int(header[1]), int(header[2])
            offsets, connectivity, index = _legacy_cells(lines, index, count, size)
            parsed["offsets"], parsed["connectivity"], parsed["cell_count"] = offsets, connectivity, count
        elif keyword in {"VERTICES", "LINES", "POLYGONS", "TRIANGLE_STRIPS"}:
            if len(header) < 3:
                raise VTKNativeError(f"Malformed {keyword} declaration.")
            count, size = int(header[1]), int(header[2])
            offsets, connectivity, index = _legacy_cells(lines, index, count, size)
            poly_sections.append((offsets, connectivity, _legacy_poly_types(keyword, offsets)))
        elif keyword == "CELL_TYPES":
            count = int(header[1])
            values, index = _legacy_numeric_lines(lines, index, count, "int32")
            parsed["cell_types"] = [int(value) for value in values]
        elif keyword == "POINT_DATA":
            association, tuple_count = "point", int(header[1])
        elif keyword == "CELL_DATA":
            association, tuple_count = "cell", int(header[1])
        elif keyword in {"SCALARS", "VECTORS", "NORMALS", "TENSORS", "TEXTURE_COORDINATES", "COLOR_SCALARS"}:
            field, index = _legacy_array(lines, index, header, association, tuple_count)
            parsed["fields"].append(field)
        elif keyword == "FIELD":
            if len(header) < 3:
                raise VTKNativeError("Malformed FIELD declaration.")
            number = int(header[2])
            for _ in range(number):
                if index >= len(lines):
                    raise VTKNativeError("FIELD section ended before all arrays were decoded.")
                field_header = lines[index].strip().split()
                index += 1
                if len(field_header) < 4:
                    raise VTKNativeError("Malformed FIELD array declaration.")
                name, components, tuples = field_header[0], int(field_header[1]), int(field_header[2])
                dtype = _normalise_dtype(field_header[3])
                values, index = _legacy_numeric_lines(lines, index, components * tuples, dtype)
                parsed["fields"].append(_array_record(
                    name=name, association="field", components=components, tuples=tuples,
                    dtype=dtype, values=values, role="field_data",
                ))
        elif keyword == "DIMENSIONS":
            dimensions = [int(value) for value in header[1:4]]
            parsed["dimensions"] = dimensions
            parsed["point_count"] = math.prod(dimensions)
            parsed["extent"] = [0, dimensions[0] - 1, 0, dimensions[1] - 1, 0, dimensions[2] - 1]
        elif keyword in {"ORIGIN", "SPACING", "ASPECT_RATIO"}:
            values = [float(value) for value in header[1:4]]
            parsed["origin" if keyword == "ORIGIN" else "spacing"] = values
        elif keyword in {"X_COORDINATES", "Y_COORDINATES", "Z_COORDINATES"}:
            count, dtype = int(header[1]), _normalise_dtype(header[2])
            values, index = _legacy_numeric_lines(lines, index, count, dtype)
            parsed["coordinate_axes"][keyword[0].lower()] = [float(value) for value in values]
        elif keyword in {"LOOKUP_TABLE", "METADATA", "INFORMATION"}:
            continue
        else:
            parsed.setdefault("unparsed_declarations", []).append(line)
    if poly_sections:
        combined_offsets: list[int] = []
        combined_connectivity: list[int] = []
        combined_types: list[int] = []
        for offsets, connectivity, types in poly_sections:
            base = len(combined_connectivity)
            combined_connectivity.extend(connectivity)
            combined_offsets.extend(base + value for value in offsets)
            combined_types.extend(types)
        parsed["offsets"] = combined_offsets
        parsed["connectivity"] = combined_connectivity
        parsed["cell_types"] = combined_types
        parsed["cell_count"] = len(combined_offsets)
    if parsed.get("dataset_type") in {"STRUCTURED_POINTS", "IMAGE_DATA"}:
        origin = parsed.get("origin", [0.0, 0.0, 0.0])
        spacing = parsed.get("spacing", [1.0, 1.0, 1.0])
        extent = parsed.get("extent")
        if extent:
            parsed["bounds"] = [
                [origin[i] + spacing[i] * extent[2 * i], origin[i] + spacing[i] * extent[2 * i + 1]]
                for i in range(3)
            ]
    elif parsed.get("coordinate_axes"):
        parsed["bounds"] = [
            [min(parsed["coordinate_axes"].get(axis, [0.0])), max(parsed["coordinate_axes"].get(axis, [0.0]))]
            for axis in ("x", "y", "z")
        ]
    parsed["dimension"] = _dataset_dimension(parsed.get("cell_types", []), parsed.get("extent"))
    return parsed


__all__ = ["parse_legacy_ascii"]
