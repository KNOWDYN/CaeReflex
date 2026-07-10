"""Dependency-free bounded reader for XML VTK datasets and collections."""
from __future__ import annotations

import base64
import math
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Any

from caereflex.execution.vtk_common import (
    VTKNativeError, _XML_TYPES, _finite, _convert_token, _array_record,
    _dataset_dimension, _COLLECTION_SUFFIXES,
)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_child(parent: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in parent if _local_name(child.tag) == name), None)


def _xml_children(parent: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in parent if _local_name(child.tag) == name]


def _parse_ints(raw: str | None, *, expected: int | None = None) -> list[int]:
    values = [int(token) for token in (raw or "").split()]
    if expected is not None and len(values) != expected:
        raise VTKNativeError(f"Expected {expected} integer values but decoded {len(values)}.")
    return values


def _parse_floats(raw: str | None, *, expected: int | None = None) -> list[float]:
    values = [float(token) for token in (raw or "").split()]
    _finite(values)
    if expected is not None and len(values) != expected:
        raise VTKNativeError(f"Expected {expected} floating-point values but decoded {len(values)}.")
    return values


def _xml_data_array(
    element: ET.Element, *, byte_order: str, header_type: str,
) -> tuple[list[int | float | bool], str, int, str | None]:
    vtk_type = element.attrib.get("type", "Float32")
    try:
        dtype, format_char = _XML_TYPES[vtk_type]
    except KeyError as exc:
        raise VTKNativeError(f"Unsupported XML VTK DataArray type: {vtk_type}") from exc
    components = int(element.attrib.get("NumberOfComponents", "1"))
    encoding = element.attrib.get("format", "ascii").lower()
    name = element.attrib.get("Name")
    text = "".join(element.itertext()).strip()
    if encoding == "ascii":
        values = [_convert_token(token, dtype) for token in text.split()]
        return _finite(values), dtype, components, name
    if encoding == "appended":
        raise VTKNativeError("Appended XML VTK arrays require an optional VTK/PyVista reader.")
    if encoding != "binary":
        raise VTKNativeError(f"Unsupported XML VTK DataArray encoding: {encoding}")
    compact = re.sub(r"\s+", "", text)
    try:
        decoded = base64.b64decode(compact, validate=True)
    except Exception as exc:
        raise VTKNativeError("Inline XML VTK base64 payload is malformed.") from exc
    header_dtype, header_char = _XML_TYPES.get(header_type, (None, None))
    if header_dtype not in {"uint32", "uint64"} or header_char is None:
        raise VTKNativeError(f"Unsupported VTK XML header_type: {header_type}")
    endian = "<" if byte_order.lower() in {"littleendian", "little"} else ">"
    header_size = struct.calcsize(header_char)
    if len(decoded) < header_size:
        raise VTKNativeError("Inline XML VTK binary payload lacks a byte-count header.")
    byte_count = int(struct.unpack(endian + header_char, decoded[:header_size])[0])
    raw = decoded[header_size:]
    if byte_count != len(raw):
        raise VTKNativeError("Inline XML VTK byte-count header does not match payload size.")
    item_size = struct.calcsize(format_char)
    if len(raw) % item_size:
        raise VTKNativeError("Inline XML VTK binary payload is not aligned to its declared type.")
    count = len(raw) // item_size
    values = list(struct.unpack(f"{endian}{count}{format_char}", raw))
    return _finite(values), dtype, components, name


def _xml_extent(element: ET.Element, root_dataset: ET.Element) -> list[int] | None:
    raw = element.attrib.get("Extent") or root_dataset.attrib.get("WholeExtent")
    return _parse_ints(raw, expected=6) if raw else None


def _xml_field_arrays(
    container: ET.Element | None,
    association: str,
    tuple_count: int | None,
    *,
    byte_order: str,
    header_type: str,
) -> list[dict[str, Any]]:
    if container is None:
        return []
    fields: list[dict[str, Any]] = []
    for index, array in enumerate(_xml_children(container, "DataArray")):
        values, dtype, components, name = _xml_data_array(
            array, byte_order=byte_order, header_type=header_type,
        )
        tuples = len(values) // components if components else 0
        if components <= 0 or tuples * components != len(values):
            raise VTKNativeError("XML VTK DataArray component count does not divide the value payload.")
        if tuple_count is not None and association in {"point", "cell"} and tuples != tuple_count:
            raise VTKNativeError(
                f"XML VTK {association} array {name or index} has {tuples} tuples; expected {tuple_count}."
            )
        fields.append(_array_record(
            name=name or f"unnamed_{association}_{index}", association=association,
            components=components, tuples=tuples, dtype=dtype, values=values,
            role="xml_data_array",
        ))
    return fields


def _poly_cell_type(section: str, count: int) -> int:
    if section == "Verts":
        return 1 if count == 1 else 2
    if section == "Lines":
        return 3 if count == 2 else 4
    if section == "Strips":
        return 6
    return 5 if count == 3 else 9 if count == 4 else 7


def parse_xml_dataset(payload: bytes) -> dict[str, Any]:
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise VTKNativeError("DTD and entity declarations are not accepted in XML VTK inputs.")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise VTKNativeError(f"Malformed XML VTK document: {exc}") from exc
    if _local_name(root.tag) != "VTKFile":
        raise VTKNativeError("XML VTK root element must be VTKFile.")
    vtk_type = root.attrib.get("type")
    if not vtk_type:
        raise VTKNativeError("XML VTK file type is missing.")
    if root.attrib.get("compressor"):
        raise VTKNativeError("Compressed XML VTK arrays require an optional VTK/PyVista reader.")
    if any(_local_name(element.tag) == "AppendedData" for element in root.iter()):
        raise VTKNativeError("Appended XML VTK arrays require an optional VTK/PyVista reader.")
    byte_order = root.attrib.get("byte_order", "LittleEndian")
    header_type = root.attrib.get("header_type", "UInt32")
    dataset = _xml_child(root, vtk_type)
    if dataset is None:
        raise VTKNativeError(f"XML VTK {vtk_type} payload element is missing.")
    pieces = _xml_children(dataset, "Piece")
    if len(pieces) != 1:
        raise VTKNativeError("The core XML reader supports exactly one Piece per dataset file.")
    piece = pieces[0]
    point_count = int(piece.attrib.get("NumberOfPoints", "0")) if "NumberOfPoints" in piece.attrib else None
    cell_count = int(piece.attrib.get("NumberOfCells", "0")) if "NumberOfCells" in piece.attrib else None
    parsed: dict[str, Any] = {
        "dataset_type": vtk_type,
        "points": [], "points_dtype": "float64", "connectivity": [], "offsets": [], "cell_types": [],
        "fields": [], "coordinate_axes": {}, "point_count": point_count, "cell_count": cell_count,
        "encoding": "xml-inline", "byte_order": byte_order,
    }
    points_container = _xml_child(piece, "Points")
    if points_container is not None:
        point_arrays = _xml_children(points_container, "DataArray")
        if len(point_arrays) != 1:
            raise VTKNativeError("XML VTK Points must contain exactly one DataArray in the core reader.")
        values, dtype, components, _ = _xml_data_array(
            point_arrays[0], byte_order=byte_order, header_type=header_type,
        )
        if components != 3 or len(values) % 3:
            raise VTKNativeError("XML VTK Points DataArray must have three components.")
        parsed["points"] = values
        parsed["points_dtype"] = dtype
        parsed["point_count"] = len(values) // 3
    cells_container = _xml_child(piece, "Cells")
    if cells_container is not None:
        named: dict[str, list[int | float | bool]] = {}
        for array in _xml_children(cells_container, "DataArray"):
            values, _, _, name = _xml_data_array(array, byte_order=byte_order, header_type=header_type)
            if name:
                named[name.lower()] = values
        parsed["connectivity"] = [int(value) for value in named.get("connectivity", [])]
        parsed["offsets"] = [int(value) for value in named.get("offsets", [])]
        parsed["cell_types"] = [int(value) for value in named.get("types", [])]
        parsed["cell_count"] = len(parsed["offsets"])
    if vtk_type == "PolyData":
        combined_connectivity: list[int] = []
        combined_offsets: list[int] = []
        combined_types: list[int] = []
        for section_name in ("Verts", "Lines", "Strips", "Polys"):
            section = _xml_child(piece, section_name)
            if section is None:
                continue
            named: dict[str, list[int | float | bool]] = {}
            for array in _xml_children(section, "DataArray"):
                values, _, _, name = _xml_data_array(array, byte_order=byte_order, header_type=header_type)
                if name:
                    named[name.lower()] = values
            connectivity = [int(value) for value in named.get("connectivity", [])]
            offsets = [int(value) for value in named.get("offsets", [])]
            previous = 0
            base = len(combined_connectivity)
            for offset in offsets:
                count = offset - previous
                combined_types.append(_poly_cell_type(section_name, count))
                previous = offset
            combined_connectivity.extend(connectivity)
            combined_offsets.extend(base + value for value in offsets)
        parsed["connectivity"] = combined_connectivity
        parsed["offsets"] = combined_offsets
        parsed["cell_types"] = combined_types
        parsed["cell_count"] = len(combined_offsets)
    extent = _xml_extent(piece, dataset)
    if extent:
        parsed["extent"] = extent
        dimensions = [
            extent[1] - extent[0] + 1,
            extent[3] - extent[2] + 1,
            extent[5] - extent[4] + 1,
        ]
        parsed["point_count"] = math.prod(dimensions)
    if vtk_type == "ImageData":
        origin = _parse_floats(dataset.attrib.get("Origin", "0 0 0"), expected=3)
        spacing = _parse_floats(dataset.attrib.get("Spacing", "1 1 1"), expected=3)
        direction = _parse_floats(dataset.attrib.get("Direction"), expected=9) if dataset.attrib.get("Direction") else None
        parsed.update({"origin": origin, "spacing": spacing, "direction": direction})
        if extent:
            parsed["bounds"] = [
                [origin[i] + spacing[i] * extent[2 * i], origin[i] + spacing[i] * extent[2 * i + 1]]
                for i in range(3)
            ]
    if vtk_type == "RectilinearGrid":
        coordinates = _xml_child(piece, "Coordinates")
        if coordinates is not None:
            axis_names = ("x", "y", "z")
            for axis, array in zip(axis_names, _xml_children(coordinates, "DataArray")):
                values, _, components, _ = _xml_data_array(
                    array, byte_order=byte_order, header_type=header_type,
                )
                if components != 1:
                    raise VTKNativeError("RectilinearGrid coordinate arrays must be scalar.")
                parsed["coordinate_axes"][axis] = [float(value) for value in values]
            parsed["bounds"] = [
                [min(parsed["coordinate_axes"].get(axis, [0.0])), max(parsed["coordinate_axes"].get(axis, [0.0]))]
                for axis in axis_names
            ]
    parsed["fields"].extend(_xml_field_arrays(
        _xml_child(piece, "PointData"), "point", parsed.get("point_count"),
        byte_order=byte_order, header_type=header_type,
    ))
    parsed["fields"].extend(_xml_field_arrays(
        _xml_child(piece, "CellData"), "cell", parsed.get("cell_count"),
        byte_order=byte_order, header_type=header_type,
    ))
    parsed["fields"].extend(_xml_field_arrays(
        _xml_child(piece, "FieldData"), "field", None,
        byte_order=byte_order, header_type=header_type,
    ))
    parsed["fields"].extend(_xml_field_arrays(
        _xml_child(dataset, "FieldData"), "field", None,
        byte_order=byte_order, header_type=header_type,
    ))
    parsed["dimension"] = _dataset_dimension(parsed.get("cell_types", []), extent)
    return parsed


def _safe_reference(raw: str) -> tuple[str | None, str | None]:
    cleaned = raw.replace("\\", "/").strip()
    pure = PurePosixPath(cleaned)
    if not cleaned or pure.is_absolute() or ".." in pure.parts or ":" in pure.parts[0]:
        return None, "reference is absolute or escapes the collection directory"
    return pure.as_posix(), None


def xml_inventory(payload: bytes, source_path: str, selected_paths: set[str]) -> dict[str, Any]:
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise VTKNativeError("DTD and entity declarations are not accepted in XML VTK inputs.")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise VTKNativeError(f"Malformed VTK XML inventory: {exc}") from exc
    vtk_type = root.attrib.get("type") if _local_name(root.tag) == "VTKFile" else _local_name(root.tag)
    base = PurePosixPath(source_path).parent
    references: list[dict[str, Any]] = []
    time_values: list[float] = []
    for element in root.iter():
        local = _local_name(element.tag)
        raw = element.attrib.get("file") or element.attrib.get("Source")
        if not raw:
            continue
        relative, reason = _safe_reference(raw)
        resolved = (base / relative).as_posix() if relative else None
        timestep: float | None = None
        if element.attrib.get("timestep") not in {None, ""}:
            try:
                timestep = float(element.attrib["timestep"])
                if math.isfinite(timestep):
                    time_values.append(timestep)
                else:
                    timestep = None
            except ValueError:
                timestep = None
        references.append({
            "element": local,
            "reference": relative or raw,
            "resolved_path": resolved,
            "safe": reason is None,
            "reason": reason,
            "selected": bool(resolved and resolved in selected_paths),
            "timestep": timestep,
            "group": element.attrib.get("group"),
            "part": element.attrib.get("part"),
            "name": element.attrib.get("name"),
        })
    return {
        "source_path": source_path,
        "kind": "vtk_collection" if Path(source_path).suffix.lower() in _COLLECTION_SUFFIXES else "vtk_parallel_inventory",
        "status": "inventoried",
        "reader": "vtk.xml-inventory",
        "vtk_type": vtk_type,
        "references": references,
        "reference_count": len(references),
        "time_values": sorted(set(time_values)),
        "time_step_count": len(set(time_values)),
        "external_references_loaded": False,
    }


__all__ = ["parse_xml_dataset", "xml_inventory"]
