"""Read-only Gmsh inspection backend.

The backend prefers the optional ``meshio`` reader for supported mesh files, then
falls back to a bounded dependency-free ASCII parser for Gmsh MSH 2.x and 4.x.
Gmsh ``.geo`` files are inspected as declarations only and are never executed.
STEP/IGES/BREP files remain fingerprint-only unless the caller explicitly enables
the isolated optional Gmsh API path; even then no mesh generation is requested.
"""
from __future__ import annotations

import ast
import hashlib
import math
import re
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from caereflex.contracts import (
    AttemptOutcome,
    DiagnosticEvent,
    DiagnosticSeverity,
    InspectionExecutionRequest,
    ParserAttempt,
)
from caereflex.core.provenance import utc_now_iso
from caereflex.execution.context import ExecutionContext, ExecutionContextError


class GmshNativeError(RuntimeError):
    """Raised when a Gmsh artefact cannot be decoded safely."""


_ELEMENT_TYPES: dict[int, tuple[str, int]] = {
    1: ("line", 1), 2: ("triangle", 2), 3: ("quad", 2), 4: ("tetra", 3),
    5: ("hexahedron", 3), 6: ("wedge", 3), 7: ("pyramid", 3), 8: ("line3", 1),
    9: ("triangle6", 2), 10: ("quad9", 2), 11: ("tetra10", 3),
    12: ("hexahedron27", 3), 13: ("wedge18", 3), 14: ("pyramid14", 3),
    15: ("vertex", 0), 16: ("quad8", 2), 17: ("hexahedron20", 3),
    18: ("wedge15", 3), 19: ("pyramid13", 3), 20: ("triangle9", 2),
    21: ("triangle10", 2), 22: ("triangle12", 2), 23: ("triangle15", 2),
    24: ("triangle15i", 2), 25: ("triangle21", 2), 26: ("line4", 1),
    27: ("line5", 1), 28: ("line6", 1), 29: ("tetra20", 3),
    30: ("tetra35", 3), 31: ("tetra56", 3), 92: ("hexahedron64", 3),
    93: ("hexahedron125", 3),
}

_MESHIO_TO_GMSH: dict[str, int] = {
    "vertex": 15, "line": 1, "line3": 8, "triangle": 2, "triangle6": 9,
    "quad": 3, "quad8": 16, "quad9": 10, "tetra": 4, "tetra10": 11,
    "hexahedron": 5, "hexahedron20": 17, "hexahedron27": 12,
    "wedge": 6, "wedge15": 18, "wedge18": 13, "pyramid": 7,
    "pyramid13": 19, "pyramid14": 14,
}

_CAD_SUFFIXES = {".step", ".stp", ".iges", ".igs", ".brep"}
_GEO_UNSUPPORTED_RE = re.compile(
    r"\b(Include|Merge|Call|SystemCall|OnelabRun|For|EndFor|If|ElseIf|Else|EndIf|"
    r"While|EndWhile|Function|Return|Macro|Extrude|BooleanUnion|BooleanDifference|"
    r"BooleanIntersection|BooleanFragments)\b",
    re.IGNORECASE,
)


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


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def _sections(text: str) -> dict[str, list[str]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    result: dict[str, list[str]] = defaultdict(list)
    index = 0
    while index < len(lines):
        marker = lines[index].strip()
        if not marker.startswith("$") or marker.startswith("$End"):
            index += 1
            continue
        name = marker[1:]
        end_marker = f"$End{name}"
        index += 1
        body: list[str] = []
        while index < len(lines) and lines[index].strip() != end_marker:
            body.append(lines[index])
            index += 1
        if index >= len(lines):
            raise GmshNativeError(f"Section ${name} is not terminated by {end_marker}.")
        result[name].append("\n".join(body).strip())
        index += 1
    return dict(result)


def _mesh_format(sections: dict[str, list[str]]) -> tuple[str, int, int]:
    items = sections.get("MeshFormat", [])
    if not items:
        raise GmshNativeError("Missing $MeshFormat section.")
    tokens = items[0].split()
    if len(tokens) < 3:
        raise GmshNativeError("Malformed $MeshFormat section.")
    try:
        return tokens[0], int(tokens[1]), int(tokens[2])
    except ValueError as exc:
        raise GmshNativeError("Invalid MeshFormat numeric token.") from exc


def _physical_names(sections: dict[str, list[str]]) -> list[dict[str, Any]]:
    items = sections.get("PhysicalNames", [])
    if not items:
        return []
    lines = [line.strip() for line in items[0].splitlines() if line.strip()]
    try:
        count = int(lines[0])
    except (IndexError, ValueError) as exc:
        raise GmshNativeError("Malformed $PhysicalNames section.") from exc
    pattern = re.compile(r"^(\d+)\s+(\d+)\s+\"(.*)\"$")
    groups: list[dict[str, Any]] = []
    for line in lines[1 : 1 + count]:
        match = pattern.match(line)
        if not match:
            raise GmshNativeError(f"Malformed physical-name record: {line}")
        groups.append({"dimension": int(match.group(1)), "tag": int(match.group(2)), "name": match.group(3)})
    if len(groups) != count:
        raise GmshNativeError(f"PhysicalNames declares {count} records but {len(groups)} were decoded.")
    return groups


def _element_descriptor(element_type: int, fallback_dimension: int | None = None) -> tuple[str, int | None]:
    descriptor = _ELEMENT_TYPES.get(element_type)
    return descriptor if descriptor else (f"gmsh_type_{element_type}", fallback_dimension)


def _parse_entities_v4(sections: dict[str, list[str]]) -> list[dict[str, Any]]:
    items = sections.get("Entities", [])
    if not items:
        return []
    lines = [line.strip() for line in items[0].splitlines() if line.strip()]
    if not lines:
        return []
    try:
        counts = [int(token) for token in lines[0].split()]
    except ValueError as exc:
        raise GmshNativeError("Malformed $Entities header.") from exc
    if len(counts) != 4:
        raise GmshNativeError("$Entities header must contain four entity counts.")
    entities: list[dict[str, Any]] = []
    cursor = 1
    for dimension, count in enumerate(counts):
        for _ in range(count):
            if cursor >= len(lines):
                raise GmshNativeError("$Entities ended before all declared entities were decoded.")
            tokens = lines[cursor].split()
            cursor += 1
            try:
                if dimension == 0:
                    tag = int(tokens[0])
                    bounds = [float(tokens[1]), float(tokens[1]), float(tokens[2]), float(tokens[2]), float(tokens[3]), float(tokens[3])]
                    index = 4
                else:
                    tag = int(tokens[0])
                    bounds = [float(value) for value in tokens[1:7]]
                    index = 7
                physical_count = int(tokens[index])
                index += 1
                physical_tags = [int(value) for value in tokens[index : index + physical_count]]
                index += physical_count
                bounding_tags: list[int] = []
                if dimension > 0 and index < len(tokens):
                    bounding_count = int(tokens[index])
                    index += 1
                    bounding_tags = [int(value) for value in tokens[index : index + bounding_count]]
            except (IndexError, ValueError) as exc:
                raise GmshNativeError(f"Malformed entity record: {lines[cursor - 1]}") from exc
            entities.append({
                "dimension": dimension,
                "tag": tag,
                "bounds": bounds,
                "physical_tags": physical_tags,
                "bounding_tags": bounding_tags,
            })
    return entities


def _parse_nodes_v2(body: str) -> tuple[list[int], list[float]]:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    try:
        count = int(lines[0])
    except (IndexError, ValueError) as exc:
        raise GmshNativeError("Malformed $Nodes header.") from exc
    tags: list[int] = []
    coordinates: list[float] = []
    for line in lines[1 : 1 + count]:
        tokens = line.split()
        if len(tokens) < 4:
            raise GmshNativeError(f"Malformed node record: {line}")
        try:
            tag = int(tokens[0])
            xyz = [float(tokens[1]), float(tokens[2]), float(tokens[3])]
        except ValueError as exc:
            raise GmshNativeError(f"Malformed node record: {line}") from exc
        if any(not math.isfinite(value) for value in xyz):
            raise GmshNativeError("Non-finite node coordinates are not accepted.")
        tags.append(tag)
        coordinates.extend(xyz)
    if len(tags) != count:
        raise GmshNativeError(f"Nodes declares {count} records but {len(tags)} were decoded.")
    if len(set(tags)) != len(tags):
        raise GmshNativeError("Duplicate node tags were found.")
    return tags, coordinates


def _parse_nodes_v4(body: str) -> tuple[list[int], list[float], list[dict[str, int]]]:
    tokens = body.split()
    if len(tokens) < 4:
        raise GmshNativeError("Malformed Gmsh 4.x $Nodes header.")
    try:
        block_count, node_count = int(tokens[0]), int(tokens[1])
    except ValueError as exc:
        raise GmshNativeError("Malformed Gmsh 4.x $Nodes header.") from exc
    cursor = 4
    tags: list[int] = []
    coordinates: list[float] = []
    blocks: list[dict[str, int]] = []
    for _ in range(block_count):
        try:
            entity_dim = int(tokens[cursor])
            entity_tag = int(tokens[cursor + 1])
            parametric = int(tokens[cursor + 2])
            count = int(tokens[cursor + 3])
        except (IndexError, ValueError) as exc:
            raise GmshNativeError("Malformed Gmsh 4.x node-block header.") from exc
        cursor += 4
        try:
            block_tags = [int(value) for value in tokens[cursor : cursor + count]]
        except ValueError as exc:
            raise GmshNativeError("Malformed node tag in Gmsh 4.x block.") from exc
        if len(block_tags) != count:
            raise GmshNativeError("Gmsh 4.x node block ended before all node tags were read.")
        cursor += count
        components = 3 + (entity_dim if parametric else 0)
        required = count * components
        raw_values = tokens[cursor : cursor + required]
        if len(raw_values) != required:
            raise GmshNativeError("Gmsh 4.x node block ended before all coordinates were read.")
        cursor += required
        for index in range(count):
            try:
                row = [float(value) for value in raw_values[index * components : (index + 1) * components]]
            except ValueError as exc:
                raise GmshNativeError("Malformed Gmsh 4.x node coordinate.") from exc
            if any(not math.isfinite(value) for value in row[:3]):
                raise GmshNativeError("Non-finite node coordinates are not accepted.")
            coordinates.extend(row[:3])
        tags.extend(block_tags)
        blocks.append({"entity_dimension": entity_dim, "entity_tag": entity_tag, "parametric": parametric, "count": count})
    if len(tags) != node_count:
        raise GmshNativeError(f"Nodes declares {node_count} records but {len(tags)} were decoded.")
    if len(set(tags)) != len(tags):
        raise GmshNativeError("Duplicate node tags were found.")
    return tags, coordinates, blocks


def _parse_elements_v2(body: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    try:
        count = int(lines[0])
    except (IndexError, ValueError) as exc:
        raise GmshNativeError("Malformed $Elements header.") from exc
    elements: list[dict[str, Any]] = []
    for line in lines[1 : 1 + count]:
        tokens = line.split()
        if len(tokens) < 4:
            raise GmshNativeError(f"Malformed element record: {line}")
        try:
            element_tag = int(tokens[0])
            element_type = int(tokens[1])
            tag_count = int(tokens[2])
            tags = [int(value) for value in tokens[3 : 3 + tag_count]]
            nodes = [int(value) for value in tokens[3 + tag_count :]]
        except ValueError as exc:
            raise GmshNativeError(f"Malformed element record: {line}") from exc
        if not nodes:
            raise GmshNativeError(f"Element {element_tag} has no node connectivity.")
        name, dimension = _element_descriptor(element_type)
        elements.append({
            "tag": element_tag,
            "type": element_type,
            "type_name": name,
            "dimension": dimension,
            "entity_tag": tags[1] if len(tags) > 1 else None,
            "physical_tags": [tags[0]] if tags else [],
            "nodes": nodes,
        })
    if len(elements) != count:
        raise GmshNativeError(f"Elements declares {count} records but {len(elements)} were decoded.")
    return elements


def _parse_elements_v4(body: str, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        raise GmshNativeError("Empty Gmsh 4.x $Elements section.")
    try:
        block_count, element_count = [int(value) for value in lines[0].split()[:2]]
    except (ValueError, IndexError) as exc:
        raise GmshNativeError("Malformed Gmsh 4.x $Elements header.") from exc
    entity_physical = {(item["dimension"], item["tag"]): item["physical_tags"] for item in entities}
    cursor = 1
    elements: list[dict[str, Any]] = []
    for _ in range(block_count):
        if cursor >= len(lines):
            raise GmshNativeError("Gmsh 4.x $Elements ended before every block was decoded.")
        try:
            entity_dim, entity_tag, element_type, count = [int(value) for value in lines[cursor].split()[:4]]
        except (ValueError, IndexError) as exc:
            raise GmshNativeError(f"Malformed element-block header: {lines[cursor]}") from exc
        cursor += 1
        name, mapped_dim = _element_descriptor(element_type, entity_dim)
        for _ in range(count):
            if cursor >= len(lines):
                raise GmshNativeError("Gmsh 4.x element block ended early.")
            try:
                values = [int(value) for value in lines[cursor].split()]
            except ValueError as exc:
                raise GmshNativeError(f"Malformed element record: {lines[cursor]}") from exc
            cursor += 1
            if len(values) < 2:
                raise GmshNativeError("Gmsh 4.x element has no connectivity.")
            elements.append({
                "tag": values[0],
                "type": element_type,
                "type_name": name,
                "dimension": mapped_dim if mapped_dim is not None else entity_dim,
                "entity_tag": entity_tag,
                "physical_tags": list(entity_physical.get((entity_dim, entity_tag), [])),
                "nodes": values[1:],
            })
    if len(elements) != element_count:
        raise GmshNativeError(f"Elements declares {element_count} records but {len(elements)} were decoded.")
    return elements


def _parse_data_section(body: str, association: str) -> dict[str, Any]:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    cursor = 0
    try:
        string_count = int(lines[cursor]); cursor += 1
        string_tags = [lines[cursor + index].strip().strip('"') for index in range(string_count)]; cursor += string_count
        real_count = int(lines[cursor]); cursor += 1
        real_tags = [float(lines[cursor + index]) for index in range(real_count)]; cursor += real_count
        integer_count = int(lines[cursor]); cursor += 1
        integer_tags = [int(lines[cursor + index]) for index in range(integer_count)]; cursor += integer_count
    except (IndexError, ValueError) as exc:
        raise GmshNativeError(f"Malformed ${association}Data header.") from exc
    components = integer_tags[1] if len(integer_tags) > 1 else 1
    declared_entries = integer_tags[2] if len(integer_tags) > 2 else len(lines) - cursor
    tags: list[int] = []
    values: list[float] = []
    for line in lines[cursor : cursor + declared_entries]:
        tokens = line.split()
        if len(tokens) < components + 1:
            raise GmshNativeError(f"Malformed {association} data record: {line}")
        try:
            tags.append(int(tokens[0]))
            row = [float(value) for value in tokens[1 : 1 + components]]
        except ValueError as exc:
            raise GmshNativeError(f"Malformed {association} data record: {line}") from exc
        if any(not math.isfinite(value) for value in row):
            raise GmshNativeError("Non-finite Gmsh data values are not accepted.")
        values.extend(row)
    if len(tags) != declared_entries:
        raise GmshNativeError(f"{association}Data declares {declared_entries} records but {len(tags)} were decoded.")
    return {
        "name": string_tags[0] if string_tags else f"unnamed_{association.lower()}_data",
        "association": "point" if association == "Node" else "cell",
        "components": components,
        "time": real_tags[0] if real_tags else None,
        "time_step": integer_tags[0] if integer_tags else None,
        "tags": tags,
        "values": values,
    }


def _parse_core_ascii(text: str) -> dict[str, Any]:
    sections = _sections(text)
    version, file_type, data_size = _mesh_format(sections)
    if file_type != 0:
        raise GmshNativeError("Binary Gmsh MSH payload detected; core ASCII decoding was not attempted.")
    try:
        major = int(version.split(".", 1)[0])
    except ValueError as exc:
        raise GmshNativeError(f"Unsupported Gmsh version token: {version}") from exc
    if major not in {2, 4}:
        raise GmshNativeError(f"Core ASCII reader supports Gmsh MSH 2.x and 4.x, not {version}.")
    if not sections.get("Nodes") or not sections.get("Elements"):
        raise GmshNativeError("A mesh requires both $Nodes and $Elements sections.")
    physical_names = _physical_names(sections)
    entities = _parse_entities_v4(sections) if major == 4 else []
    if major == 2:
        node_tags, coordinates = _parse_nodes_v2(sections["Nodes"][0])
        node_blocks: list[dict[str, int]] = []
        elements = _parse_elements_v2(sections["Elements"][0])
    else:
        node_tags, coordinates, node_blocks = _parse_nodes_v4(sections["Nodes"][0])
        elements = _parse_elements_v4(sections["Elements"][0], entities)
    fields = [_parse_data_section(body, "Node") for body in sections.get("NodeData", [])]
    fields.extend(_parse_data_section(body, "Element") for body in sections.get("ElementData", []))
    return {
        "mesh_format_version": version,
        "file_type": file_type,
        "data_size": data_size,
        "physical_names": physical_names,
        "entities": entities,
        "node_blocks": node_blocks,
        "node_tags": node_tags,
        "coordinates": coordinates,
        "elements": elements,
        "fields": fields,
        "unsupported_sections": sorted(name for name in sections if name not in {
            "MeshFormat", "PhysicalNames", "Entities", "Nodes", "Elements", "NodeData", "ElementData"
        }),
    }


def _bounds(coordinates: list[float]) -> list[list[float]] | None:
    if not coordinates:
        return None
    axes = [coordinates[index::3] for index in range(3)]
    return [[min(axis), max(axis)] for axis in axes]


def _register_mesh_arrays(
    context: ExecutionContext,
    *,
    source_path: str,
    asset_id: str,
    node_tags: list[int],
    coordinates: list[float],
    elements: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    backend_version: str,
    coordinate_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    node_tag_ref = context.register_numeric_array(
        node_tags, dtype="int64", shape=(len(node_tags),), source_asset_id=asset_id,
        source_path=source_path, association="point", backend_version=backend_version,
        metadata={"role": "node_tags", "tag_space": "gmsh"},
    )
    points_ref = context.register_numeric_array(
        coordinates, dtype="float64", shape=(len(node_tags), 3), source_asset_id=asset_id,
        source_path=source_path, association="point", component_names=["x", "y", "z"],
        coordinate_frame_ref="gmsh_model_frame", backend_version=backend_version,
        metadata={"role": "mesh_points", "length_units": "unresolved", **(coordinate_metadata or {})},
    )
    element_tags: list[int] = []
    element_types: list[int] = []
    entity_dimensions: list[int] = []
    entity_tags: list[int] = []
    connectivity: list[int] = []
    offsets: list[int] = [0]
    physical_offsets: list[int] = [0]
    physical_tags: list[int] = []
    for element in elements:
        element_tags.append(int(element["tag"]))
        element_types.append(int(element["type"]))
        entity_dimensions.append(int(element["dimension"]) if element.get("dimension") is not None else -1)
        entity_tags.append(int(element["entity_tag"]) if element.get("entity_tag") is not None else -1)
        connectivity.extend(int(value) for value in element["nodes"])
        offsets.append(len(connectivity))
        physical_tags.extend(int(value) for value in element.get("physical_tags", []))
        physical_offsets.append(len(physical_tags))
    arrays: dict[str, Any] = {"node_tags_array_id": node_tag_ref.array_id, "points_array_id": points_ref.array_id}
    for role, values, dtype in (
        ("element_tags", element_tags, "int64"),
        ("element_types", element_types, "int32"),
        ("element_entity_dimensions", entity_dimensions, "int32"),
        ("element_entity_tags", entity_tags, "int64"),
        ("element_connectivity", connectivity, "int64"),
        ("element_offsets", offsets, "int64"),
        ("element_physical_tags", physical_tags, "int64"),
        ("element_physical_offsets", physical_offsets, "int64"),
    ):
        ref = context.register_numeric_array(
            values, dtype=dtype, shape=(len(values),), source_asset_id=asset_id,
            source_path=source_path, association="cell", backend_version=backend_version,
            metadata={"role": role, "connectivity_space": "gmsh_node_tags"},
        )
        arrays[f"{role}_array_id"] = ref.array_id
    field_summaries: list[dict[str, Any]] = []
    for field in fields:
        components = int(field["components"])
        tag_ref = context.register_numeric_array(
            field["tags"], dtype="int64", shape=(len(field["tags"]),), source_asset_id=asset_id,
            source_path=source_path, association=field["association"], time_index=field.get("time"),
            backend_version=backend_version, metadata={"role": "field_entity_tags", "field_name": field["name"]},
        )
        component_names = [] if components == 1 else [f"c{index}" for index in range(components)]
        shape = (len(field["tags"]),) if components == 1 else (len(field["tags"]), components)
        value_ref = context.register_numeric_array(
            field["values"], dtype="float64", shape=shape, source_asset_id=asset_id,
            source_path=source_path, association=field["association"], component_names=component_names,
            time_index=field.get("time"), backend_version=backend_version,
            metadata={"role": "field_values", "field_name": field["name"], "units": "unresolved"},
        )
        field_summaries.append({
            "name": field["name"], "association": field["association"], "components": components,
            "entries": len(field["tags"]), "time": field.get("time"), "time_step": field.get("time_step"),
            "tags_array_id": tag_ref.array_id, "array_id": value_ref.array_id, "units": "unresolved",
        })
    arrays["field_arrays"] = field_summaries
    return arrays


def _physical_group_summary(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    names = {(item["dimension"], item["tag"]): item["name"] for item in parsed.get("physical_names", [])}
    counts: Counter[tuple[int | None, int]] = Counter()
    for element in parsed.get("elements", []):
        for tag in element.get("physical_tags", []):
            counts[(element.get("dimension"), tag)] += 1
    keys = set(names) | set(counts)
    return [{
        "dimension": dimension, "tag": tag, "name": names.get((dimension, tag)),
        "element_count": counts.get((dimension, tag), 0),
    } for dimension, tag in sorted(keys, key=lambda item: ((-1 if item[0] is None else item[0]), item[1]))]


def _core_summary(parsed: dict[str, Any], context: ExecutionContext, source_path: str, asset_id: str, backend_version: str) -> dict[str, Any]:
    elements = parsed["elements"]
    counts = Counter((element["type"], element["type_name"], element.get("dimension")) for element in elements)
    arrays = _register_mesh_arrays(
        context, source_path=source_path, asset_id=asset_id, node_tags=parsed["node_tags"],
        coordinates=parsed["coordinates"], elements=elements, fields=parsed["fields"], backend_version=backend_version,
    )
    dimensions = [element["dimension"] for element in elements if element.get("dimension") is not None]
    return {
        "source_path": source_path, "kind": "mesh", "status": "decoded", "reader": "gmsh.core-ascii",
        "mesh_format_version": parsed["mesh_format_version"], "binary": False, "data_size": parsed["data_size"],
        "dimension": max(dimensions) if dimensions else None, "node_count": len(parsed["node_tags"]),
        "element_count": len(elements), "bounds": _bounds(parsed["coordinates"]),
        "cell_types": [{"gmsh_type": et, "name": name, "dimension": dim, "count": count}
                       for (et, name, dim), count in sorted(counts.items())],
        "physical_groups": _physical_group_summary(parsed), "entities": parsed["entities"],
        "node_blocks": parsed["node_blocks"], "fields": arrays.pop("field_arrays"), "arrays": arrays,
        "unsupported_sections": parsed["unsupported_sections"], "coordinate_units": "unresolved",
    }


def _meshio_summary(payload: bytes, suffix: str, context: ExecutionContext, source_path: str, asset_id: str, backend_version: str) -> dict[str, Any]:
    try:
        import meshio  # type: ignore
    except Exception as exc:
        raise ModuleNotFoundError("meshio is not installed") from exc
    temporary = context.work_root / f"gmsh-input{suffix or '.msh'}"
    temporary.write_bytes(payload)
    mesh = meshio.read(str(temporary))
    rows = mesh.points.tolist()
    if not rows:
        raise GmshNativeError("meshio returned no points.")
    coordinates = [float(value) for row in rows for value in list(row)[:3]]
    if len(coordinates) != len(rows) * 3:
        raise GmshNativeError("meshio point coordinates are not three-dimensional.")
    node_tags = list(range(1, len(rows) + 1))
    physical_by_block = mesh.cell_data.get("gmsh:physical", []) if hasattr(mesh, "cell_data") else []
    geometrical_by_block = mesh.cell_data.get("gmsh:geometrical", []) if hasattr(mesh, "cell_data") else []
    elements: list[dict[str, Any]] = []
    block_element_tags: list[list[int]] = []
    next_tag = 1
    for block_index, block in enumerate(mesh.cells):
        element_type = _MESHIO_TO_GMSH.get(block.type, -1000 - block_index)
        name, dimension = _element_descriptor(element_type)
        if element_type < 0:
            name, dimension = block.type, None
        block_tags: list[int] = []
        block_rows = block.data.tolist()
        physical_values = physical_by_block[block_index].tolist() if block_index < len(physical_by_block) else []
        entity_values = geometrical_by_block[block_index].tolist() if block_index < len(geometrical_by_block) else []
        for row_index, row in enumerate(block_rows):
            block_tags.append(next_tag)
            elements.append({
                "tag": next_tag, "type": element_type, "type_name": name, "dimension": dimension,
                "entity_tag": int(entity_values[row_index]) if row_index < len(entity_values) else None,
                "physical_tags": [int(physical_values[row_index])] if row_index < len(physical_values) else [],
                "nodes": [int(value) + 1 for value in row],
            })
            next_tag += 1
        block_element_tags.append(block_tags)
    fields: list[dict[str, Any]] = []
    for name, values in getattr(mesh, "point_data", {}).items():
        data = values.tolist()
        if data and isinstance(data[0], list):
            components = len(data[0]); flattened = [float(value) for row in data for value in row]
        else:
            components = 1; flattened = [float(value) for value in data]
        fields.append({"name": name, "association": "point", "components": components, "time": None,
                       "time_step": None, "tags": node_tags[:len(data)], "values": flattened})
    for name, blocks in getattr(mesh, "cell_data", {}).items():
        if name in {"gmsh:physical", "gmsh:geometrical"}:
            continue
        values_flat: list[float] = []
        tags_flat: list[int] = []
        components: int | None = None
        for block_index, values in enumerate(blocks):
            data = values.tolist()
            if not data:
                continue
            current_components = len(data[0]) if isinstance(data[0], list) else 1
            if components is None:
                components = current_components
            if components != current_components:
                raise GmshNativeError(f"meshio cell-data field {name!r} changes component count between blocks.")
            values_flat.extend(float(value) for row in data for value in (row if isinstance(row, list) else [row]))
            tags_flat.extend(block_element_tags[block_index][:len(data)])
        if components is not None:
            fields.append({"name": name, "association": "cell", "components": components, "time": None,
                           "time_step": None, "tags": tags_flat, "values": values_flat})
    physical_names = []
    for name, value in getattr(mesh, "field_data", {}).items():
        row = value.tolist() if hasattr(value, "tolist") else list(value)
        if len(row) >= 2:
            physical_names.append({"name": name, "tag": int(row[0]), "dimension": int(row[1])})
    parsed = {"physical_names": physical_names, "elements": elements}
    arrays = _register_mesh_arrays(
        context, source_path=source_path, asset_id=asset_id, node_tags=node_tags,
        coordinates=coordinates, elements=elements, fields=fields, backend_version=backend_version,
        coordinate_metadata={"meshio_point_tags": "synthetic-contiguous"},
    )
    counts = Counter((element["type"], element["type_name"], element.get("dimension")) for element in elements)
    dimensions = [item["dimension"] for item in elements if item.get("dimension") is not None]
    return {
        "source_path": source_path, "kind": "mesh", "status": "decoded", "reader": "meshio",
        "mesh_format_version": None, "binary": None, "dimension": max(dimensions) if dimensions else None,
        "node_count": len(node_tags), "element_count": len(elements), "bounds": _bounds(coordinates),
        "cell_types": [{"gmsh_type": et, "name": name, "dimension": dim, "count": count}
                       for (et, name, dim), count in sorted(counts.items())],
        "physical_groups": _physical_group_summary(parsed), "entities": [], "node_blocks": [],
        "fields": arrays.pop("field_arrays"), "arrays": arrays, "unsupported_sections": [],
        "coordinate_units": "unresolved",
    }


def _safe_numeric(expression: str, variables: dict[str, float]) -> float:
    try:
        node = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise GmshNativeError(f"Unsafe or invalid numeric expression: {expression}") from exc
    def evaluate(item: ast.AST) -> float:
        if isinstance(item, ast.Expression): return evaluate(item.body)
        if isinstance(item, ast.Constant) and isinstance(item.value, (int, float)): return float(item.value)
        if isinstance(item, ast.Name) and item.id in variables: return float(variables[item.id])
        if isinstance(item, ast.UnaryOp) and isinstance(item.op, (ast.UAdd, ast.USub)):
            value = evaluate(item.operand); return value if isinstance(item.op, ast.UAdd) else -value
        if isinstance(item, ast.BinOp) and isinstance(item.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod)):
            left, right = evaluate(item.left), evaluate(item.right)
            if isinstance(item.op, ast.Add): return left + right
            if isinstance(item.op, ast.Sub): return left - right
            if isinstance(item.op, ast.Mult): return left * right
            if isinstance(item.op, ast.Div): return left / right
            if isinstance(item.op, ast.Pow): return left ** right
            return left % right
        raise GmshNativeError(f"Expression is outside the declaration-only numeric subset: {expression}")
    value = evaluate(node)
    if not math.isfinite(value):
        raise GmshNativeError("Non-finite .geo numeric values are not accepted.")
    return value


def _split_csv(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(text):
        if char in "([": depth += 1
        elif char in ")]": depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip()); start = index + 1
    parts.append(text[start:].strip())
    return [item for item in parts if item]


def _int_expression(expression: str, variables: dict[str, float]) -> int:
    value = _safe_numeric(expression, variables)
    rounded = int(round(value))
    if abs(value - rounded) > 1e-9:
        raise GmshNativeError(f"Expected an integer declaration tag, received {expression}.")
    return rounded


def _parse_member_list(text: str, variables: dict[str, float]) -> list[int]:
    members: list[int] = []
    for item in _split_csv(text):
        if ":" in item:
            pieces = [piece.strip() for piece in item.split(":")]
            if len(pieces) in {2, 3}:
                start = _int_expression(pieces[0], variables)
                stop = _int_expression(pieces[-1], variables)
                step = _int_expression(pieces[1], variables) if len(pieces) == 3 else (1 if stop >= start else -1)
                if step == 0: raise GmshNativeError("A .geo declaration range cannot have zero step.")
                members.extend(range(start, stop + (1 if step > 0 else -1), step)); continue
        members.append(_int_expression(item, variables))
    return members


def _parse_geo(text: str) -> dict[str, Any]:
    clean = _strip_comments(text)
    variables: dict[str, float] = {}
    pending = [(m.group(1), m.group(2)) for m in re.finditer(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;{}]+);", clean)]
    for _ in range(max(1, len(pending))):
        changed = False
        remaining: list[tuple[str, str]] = []
        for name, expression in pending:
            try:
                variables[name] = _safe_numeric(expression, variables); changed = True
            except Exception:
                remaining.append((name, expression))
        pending = remaining
        if not changed: break
    unresolved_variables = sorted(name for name, _ in pending)
    points: list[dict[str, Any]] = []
    unresolved_points: list[str] = []
    for match in re.finditer(r"\bPoint\s*\(([^)]*)\)\s*=\s*\{([^}]*)\}\s*;", clean, flags=re.IGNORECASE):
        try:
            values = _split_csv(match.group(2))
            if len(values) < 3: raise GmshNativeError("Point declaration contains fewer than three coordinates.")
            points.append({"tag": _int_expression(match.group(1), variables),
                           "coordinates": [_safe_numeric(item, variables) for item in values[:3]]})
        except Exception:
            unresolved_points.append(match.group(0).strip())
    entities: list[dict[str, Any]] = []
    patterns = [
        ("curve", 1, r"\b(Line|Circle|Ellipse|Spline|BSpline|Bezier)\s*\(([^)]*)\)\s*=\s*\{([^}]*)\}\s*;"),
        ("curve_loop", 1, r"\b(?:Curve|Line)\s+Loop\s*\(([^)]*)\)\s*=\s*\{([^}]*)\}\s*;"),
        ("surface", 2, r"\b(?:Plane\s+Surface|Ruled\s+Surface|Surface)\s*\(([^)]*)\)\s*=\s*\{([^}]*)\}\s*;"),
        ("surface_loop", 2, r"\bSurface\s+Loop\s*\(([^)]*)\)\s*=\s*\{([^}]*)\}\s*;"),
        ("volume", 3, r"\bVolume\s*\(([^)]*)\)\s*=\s*\{([^}]*)\}\s*;"),
    ]
    unresolved_entities: list[str] = []
    for kind, dimension, pattern in patterns:
        for match in re.finditer(pattern, clean, flags=re.IGNORECASE):
            groups = match.groups()
            if kind == "curve": subtype, raw_tag, raw_members = groups
            else: subtype, raw_tag, raw_members = kind, groups[0], groups[1]
            try:
                entities.append({"kind": kind, "subtype": str(subtype), "dimension": dimension,
                                 "tag": _int_expression(raw_tag, variables),
                                 "members": _parse_member_list(raw_members, variables)})
            except Exception:
                unresolved_entities.append(match.group(0).strip())
    physical_groups: list[dict[str, Any]] = []
    unresolved_physical: list[str] = []
    kind_dimension = {"point": 0, "curve": 1, "line": 1, "surface": 2, "volume": 3}
    pattern = re.compile(r"\bPhysical\s+(Point|Curve|Line|Surface|Volume)\s*\(([^)]*)\)\s*=\s*\{([^}]*)\}\s*;", re.IGNORECASE)
    for match in pattern.finditer(clean):
        kind = match.group(1).lower(); arguments = _split_csv(match.group(2)); name = None; tag = None
        try:
            if arguments and arguments[0].strip().startswith('"') and arguments[0].strip().endswith('"'):
                name = arguments[0].strip()[1:-1]
                if len(arguments) > 1: tag = _int_expression(arguments[1], variables)
            elif arguments: tag = _int_expression(arguments[0], variables)
            physical_groups.append({"kind": kind, "dimension": kind_dimension[kind], "name": name, "tag": tag,
                                    "members": _parse_member_list(match.group(3), variables)})
        except Exception:
            unresolved_physical.append(match.group(0).strip())
    unsupported = sorted({match.group(1) for match in _GEO_UNSUPPORTED_RE.finditer(clean)}, key=str.lower)
    dimension = max([entity["dimension"] for entity in entities] + [0 if points else -1]) if (entities or points) else None
    return {
        "variables": variables, "unresolved_variables": unresolved_variables, "points": points,
        "entities": entities, "physical_groups": physical_groups, "dimension": dimension,
        "unsupported_constructs": unsupported,
        "unresolved_declarations": {"points": unresolved_points, "entities": unresolved_entities,
                                    "physical_groups": unresolved_physical},
    }


def _geo_summary(parsed: dict[str, Any], context: ExecutionContext, source_path: str, asset_id: str, backend_version: str) -> dict[str, Any]:
    points = parsed["points"]
    arrays: dict[str, Any] = {}
    if points:
        tags = [item["tag"] for item in points]
        coordinates = [value for item in points for value in item["coordinates"]]
        tag_ref = context.register_numeric_array(tags, dtype="int64", shape=(len(tags),), source_asset_id=asset_id,
                                                 source_path=source_path, association="point", backend_version=backend_version,
                                                 metadata={"role": "geo_point_tags"})
        point_ref = context.register_numeric_array(coordinates, dtype="float64", shape=(len(tags), 3), source_asset_id=asset_id,
                                                   source_path=source_path, association="point", component_names=["x", "y", "z"],
                                                   coordinate_frame_ref="gmsh_model_frame", backend_version=backend_version,
                                                   metadata={"role": "geo_points", "length_units": "unresolved"})
        arrays = {"point_tags_array_id": tag_ref.array_id, "points_array_id": point_ref.array_id}
    counts = Counter(item["kind"] for item in parsed["entities"])
    unresolved = parsed["unresolved_declarations"]
    return {
        "source_path": source_path, "kind": "geo_declarations",
        "status": "partial" if any(unresolved.values()) or parsed["unsupported_constructs"] else "decoded",
        "reader": "gmsh.geo-declaration-parser", "executed": False, "dimension": parsed["dimension"],
        "point_count": len(points), "bounds": _bounds([value for item in points for value in item["coordinates"]]),
        "entity_counts": dict(sorted(counts.items())), "entities": parsed["entities"],
        "physical_groups": parsed["physical_groups"], "variables": parsed["variables"],
        "unresolved_variables": parsed["unresolved_variables"], "unresolved_declarations": unresolved,
        "unsupported_constructs": parsed["unsupported_constructs"], "arrays": arrays,
        "coordinate_units": "unresolved",
    }


def _fingerprint(payload: bytes, source_path: str, suffix: str) -> dict[str, Any]:
    return {"source_path": source_path, "kind": "cad_fingerprint" if suffix in _CAD_SUFFIXES else "file_fingerprint",
            "status": "fingerprinted", "suffix": suffix, "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(), "decoded": False}


def _gmsh_api_summary(payload: bytes, suffix: str, context: ExecutionContext, source_path: str, asset_id: str, backend_version: str) -> dict[str, Any]:
    if suffix == ".geo":
        raise GmshNativeError("The Gmsh API is never used to execute .geo files in Gate 5C.")
    try:
        import gmsh  # type: ignore
    except Exception as exc:
        raise ModuleNotFoundError("gmsh is not installed") from exc
    temporary = context.work_root / f"gmsh-api-input{suffix}"
    temporary.write_bytes(payload)
    initialized = False
    try:
        gmsh.initialize(["caereflex", "-nopopup"]); initialized = True
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(temporary))
        entities = []
        for dimension, tag in gmsh.model.getEntities():
            entities.append({"dimension": int(dimension), "tag": int(tag),
                             "bounds": [float(value) for value in gmsh.model.getBoundingBox(dimension, tag)],
                             "physical_tags": [int(value) for value in gmsh.model.getPhysicalGroupsForEntity(dimension, tag)]})
        node_tags_raw, coordinates_raw, _ = gmsh.model.mesh.getNodes()
        node_tags = [int(value) for value in node_tags_raw.tolist()]
        coordinates = [float(value) for value in coordinates_raw.tolist()]
        elements: list[dict[str, Any]] = []
        element_types, element_tags_blocks, node_tags_blocks = gmsh.model.mesh.getElements()
        for block_index, raw_type in enumerate(element_types):
            element_type = int(raw_type)
            properties = gmsh.model.mesh.getElementProperties(element_type)
            name, dimension, nodes_per_element = str(properties[0]), int(properties[1]), int(properties[3])
            tags_block = [int(value) for value in element_tags_blocks[block_index].tolist()]
            nodes_block = [int(value) for value in node_tags_blocks[block_index].tolist()]
            for index, element_tag in enumerate(tags_block):
                start = index * nodes_per_element
                elements.append({"tag": element_tag, "type": element_type, "type_name": name,
                                 "dimension": dimension, "entity_tag": None, "physical_tags": [],
                                 "nodes": nodes_block[start:start + nodes_per_element]})
        arrays: dict[str, Any] = {}
        if node_tags:
            arrays = _register_mesh_arrays(context, source_path=source_path, asset_id=asset_id, node_tags=node_tags,
                                           coordinates=coordinates, elements=elements, fields=[], backend_version=backend_version,
                                           coordinate_metadata={"reader": "gmsh-api", "mesh_generation_requested": False})
            arrays.pop("field_arrays", None)
        return {"source_path": source_path, "kind": "cad_or_mesh_model", "status": "decoded", "reader": "gmsh-api",
                "mesh_generation_requested": False, "dimension": max((item["dimension"] for item in entities), default=None),
                "entity_count": len(entities), "entities": entities, "node_count": len(node_tags),
                "element_count": len(elements), "bounds": _bounds(coordinates), "arrays": arrays,
                "coordinate_units": "unresolved"}
    finally:
        if initialized: gmsh.finalize()


class GmshNativeBackend:
    backend_id = "gmsh.native"
    backend_version = "1.0.0"

    def execute(self, request: InspectionExecutionRequest, context: ExecutionContext) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "format": "Gmsh", "reader": self.backend_id, "files": [],
            "mesh_count": 0, "geo_count": 0, "cad_count": 0,
            "non_execution_guarantees": [
                ".geo files are parsed as declarations and never evaluated",
                "mesh generation is never requested", "source files are never modified",
            ],
        }
        selected = [path for path in request.plan.selected_paths
                    if Path(path).suffix.lower() in ({".msh", ".geo"} | _CAD_SUFFIXES)]
        for index, source_path in enumerate(selected, start=1):
            suffix = Path(source_path).suffix.lower()
            asset_id = f"asset_gmsh_{index}"
            read_started = utc_now_iso()
            try:
                payload = context.read_bytes(source_path)
            except (ExecutionContextError, OSError) as exc:
                diagnostic = DiagnosticEvent(code="CRX-GMSH-READ-001", severity=DiagnosticSeverity.warning,
                    message=f"Gmsh source could not be read within the execution budget: {exc}", source_path=source_path,
                    parser=self.backend_id, information_lost=["mesh_or_geometry_evidence"])
                _attempt(context, stage="read_source", backend_id=self.backend_id, outcome=AttemptOutcome.failed,
                         started_at=read_started, error=exc, diagnostics=[diagnostic],
                         information_lost=["mesh_or_geometry_evidence"])
                continue
            if suffix == ".msh":
                summary["mesh_count"] += 1
                file_summary: dict[str, Any] | None = None
                meshio_started = utc_now_iso()
                if request.backend_options.get("disable_meshio") is True:
                    _attempt(context, stage="meshio_decode", backend_id="gmsh.meshio", outcome=AttemptOutcome.skipped,
                             started_at=meshio_started, fallback_to="gmsh.core-ascii", metadata={"reason": "disabled_by_request"})
                else:
                    try:
                        file_summary = _meshio_summary(payload, suffix, context, source_path, asset_id, self.backend_version)
                        _attempt(context, stage="meshio_decode", backend_id="gmsh.meshio", outcome=AttemptOutcome.success,
                                 started_at=meshio_started)
                    except ModuleNotFoundError as exc:
                        _attempt(context, stage="meshio_decode", backend_id="gmsh.meshio", outcome=AttemptOutcome.skipped,
                                 started_at=meshio_started, error=exc, fallback_to="gmsh.core-ascii",
                                 metadata={"reason": "optional_dependency_unavailable"})
                    except Exception as exc:
                        diagnostic = DiagnosticEvent(code="CRX-GMSH-MESHIO-FALLBACK-001", severity=DiagnosticSeverity.info,
                            message=f"meshio did not decode {source_path}; the bounded core ASCII reader was tried next: {exc}",
                            source_path=source_path, parser="gmsh.meshio", fallback_used="gmsh.core-ascii")
                        _attempt(context, stage="meshio_decode", backend_id="gmsh.meshio", outcome=AttemptOutcome.failed,
                                 started_at=meshio_started, error=exc, fallback_to="gmsh.core-ascii", diagnostics=[diagnostic])
                if file_summary is None:
                    core_started = utc_now_iso()
                    try:
                        parsed = _parse_core_ascii(payload.decode("utf-8", errors="strict"))
                        file_summary = _core_summary(parsed, context, source_path, asset_id, self.backend_version)
                        _attempt(context, stage="core_ascii_decode", backend_id="gmsh.core-ascii",
                                 outcome=AttemptOutcome.success, started_at=core_started)
                    except (UnicodeDecodeError, GmshNativeError, ExecutionContextError) as exc:
                        diagnostic = DiagnosticEvent(code="CRX-GMSH-MSH-FALLBACK-001", severity=DiagnosticSeverity.warning,
                            message=f"Gmsh mesh decoding fell back to a fingerprint: {exc}", source_path=source_path,
                            parser="gmsh.core-ascii", fallback_used="fingerprint-only",
                            information_lost=["nodes", "elements", "physical_groups", "fields", "lazy_arrays"])
                        _attempt(context, stage="core_ascii_decode", backend_id="gmsh.core-ascii",
                                 outcome=AttemptOutcome.failed, started_at=core_started, error=exc,
                                 fallback_to="fingerprint-only",
                                 information_lost=["nodes", "elements", "physical_groups", "fields", "lazy_arrays"],
                                 diagnostics=[diagnostic])
                        file_summary = _fingerprint(payload, source_path, suffix)
                summary["files"].append(file_summary)
                continue
            if suffix == ".geo":
                summary["geo_count"] += 1
                started = utc_now_iso()
                try:
                    parsed = _parse_geo(payload.decode("utf-8", errors="strict"))
                    file_summary = _geo_summary(parsed, context, source_path, asset_id, self.backend_version)
                    diagnostics: list[DiagnosticEvent] = []
                    if parsed["unsupported_constructs"] or any(parsed["unresolved_declarations"].values()):
                        diagnostics.append(DiagnosticEvent(code="CRX-GMSH-GEO-PARTIAL-001", severity=DiagnosticSeverity.warning,
                            message="The .geo file contains declarations outside the safe literal subset; they were preserved as unresolved and not executed.",
                            source_path=source_path, parser="gmsh.geo-declaration-parser",
                            details={"unsupported_constructs": parsed["unsupported_constructs"],
                                     "unresolved_counts": {key: len(value) for key, value in parsed["unresolved_declarations"].items()}},
                            information_lost=["procedural_geometry_result"]))
                    _attempt(context, stage="geo_declaration_parse", backend_id="gmsh.geo-declaration-parser",
                             outcome=AttemptOutcome.success, started_at=started,
                             information_lost=["procedural_geometry_result"] if diagnostics else [],
                             diagnostics=diagnostics, metadata={"executed": False})
                    summary["files"].append(file_summary)
                except (UnicodeDecodeError, GmshNativeError) as exc:
                    diagnostic = DiagnosticEvent(code="CRX-GMSH-GEO-PARTIAL-001", severity=DiagnosticSeverity.warning,
                        message=f"The .geo declaration parser fell back to a fingerprint without executing the file: {exc}",
                        source_path=source_path, parser="gmsh.geo-declaration-parser", fallback_used="fingerprint-only",
                        information_lost=["geometry_declarations"])
                    _attempt(context, stage="geo_declaration_parse", backend_id="gmsh.geo-declaration-parser",
                             outcome=AttemptOutcome.failed, started_at=started, error=exc, fallback_to="fingerprint-only",
                             information_lost=["geometry_declarations"], diagnostics=[diagnostic], metadata={"executed": False})
                    summary["files"].append(_fingerprint(payload, source_path, suffix))
                continue
            summary["cad_count"] += 1
            if request.backend_options.get("enable_gmsh_api") is True:
                started = utc_now_iso()
                try:
                    file_summary = _gmsh_api_summary(payload, suffix, context, source_path, asset_id, self.backend_version)
                    _attempt(context, stage="gmsh_api_decode", backend_id="gmsh.api", outcome=AttemptOutcome.success,
                             started_at=started, metadata={"explicit_opt_in": True, "mesh_generation_requested": False})
                    summary["files"].append(file_summary)
                    continue
                except Exception as exc:
                    diagnostic = DiagnosticEvent(code="CRX-GMSH-API-FALLBACK-001", severity=DiagnosticSeverity.warning,
                        message=f"The explicitly enabled Gmsh API path failed and fell back to a fingerprint: {exc}",
                        source_path=source_path, parser="gmsh.api", fallback_used="fingerprint-only",
                        information_lost=["cad_entities", "mesh_entities"])
                    _attempt(context, stage="gmsh_api_decode", backend_id="gmsh.api", outcome=AttemptOutcome.failed,
                             started_at=started, error=exc, fallback_to="fingerprint-only",
                             information_lost=["cad_entities", "mesh_entities"], diagnostics=[diagnostic],
                             metadata={"explicit_opt_in": True, "mesh_generation_requested": False})
            else:
                _attempt(context, stage="gmsh_api_decode", backend_id="gmsh.api", outcome=AttemptOutcome.skipped,
                         started_at=utc_now_iso(), fallback_to="fingerprint-only", information_lost=["cad_entities"],
                         metadata={"reason": "explicit_opt_in_required", "mesh_generation_requested": False})
            diagnostic = DiagnosticEvent(code="CRX-GMSH-CAD-FINGERPRINT-001", severity=DiagnosticSeverity.info,
                message=f"{suffix} geometry was fingerprinted only; enable the optional isolated Gmsh API explicitly for entity inspection.",
                source_path=source_path, parser=self.backend_id, fallback_used="fingerprint-only",
                information_lost=["cad_entities", "topology"])
            context.diagnostics.append(diagnostic)
            summary["files"].append(_fingerprint(payload, source_path, suffix))
        summary["array_count"] = len(context.arrays)
        summary["diagnostic_count"] = len(context.diagnostics)
        return {"summary": summary}
