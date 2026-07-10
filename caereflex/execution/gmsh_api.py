"""Compatibility layer for explicitly enabled Gmsh API inspection.

Gmsh Python releases may return either Python lists or NumPy-like arrays from the
same API calls. This module normalises both forms without introducing NumPy as a
core dependency. It is loaded only by the built-in Gmsh backend and never receives
``.geo`` scripts.
"""
from __future__ import annotations

from typing import Any

from caereflex.execution.context import ExecutionContext
from caereflex.execution.gmsh_native import GmshNativeError, _bounds, _register_mesh_arrays


def _as_list(value: Any) -> list[Any]:
    converted = value.tolist() if hasattr(value, "tolist") else value
    if converted is None:
        return []
    if isinstance(converted, list):
        return converted
    if isinstance(converted, tuple):
        return list(converted)
    try:
        return list(converted)
    except TypeError:
        return [converted]


def gmsh_api_summary(
    payload: bytes,
    suffix: str,
    context: ExecutionContext,
    source_path: str,
    asset_id: str,
    backend_version: str,
) -> dict[str, Any]:
    """Inspect an explicitly opted-in CAD or existing-mesh model through Gmsh.

    The function opens a worker-local copy, inventories model entities and any
    mesh already present, and never calls a mesh-generation operation.
    """

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
        gmsh.initialize(["caereflex", "-nopopup"])
        initialized = True
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(temporary))

        entities: list[dict[str, Any]] = []
        for raw_dimension, raw_tag in gmsh.model.getEntities():
            dimension = int(raw_dimension)
            tag = int(raw_tag)
            entities.append(
                {
                    "dimension": dimension,
                    "tag": tag,
                    "bounds": [float(value) for value in _as_list(gmsh.model.getBoundingBox(dimension, tag))],
                    "physical_tags": [
                        int(value)
                        for value in _as_list(gmsh.model.getPhysicalGroupsForEntity(dimension, tag))
                    ],
                }
            )

        node_tags_raw, coordinates_raw, _ = gmsh.model.mesh.getNodes()
        node_tags = [int(value) for value in _as_list(node_tags_raw)]
        coordinates = [float(value) for value in _as_list(coordinates_raw)]

        elements: list[dict[str, Any]] = []
        element_types_raw, element_tags_blocks_raw, node_tags_blocks_raw = gmsh.model.mesh.getElements()
        element_types = _as_list(element_types_raw)
        element_tags_blocks = _as_list(element_tags_blocks_raw)
        node_tags_blocks = _as_list(node_tags_blocks_raw)
        for block_index, raw_type in enumerate(element_types):
            element_type = int(raw_type)
            properties = _as_list(gmsh.model.mesh.getElementProperties(element_type))
            if len(properties) < 4:
                raise GmshNativeError(f"Gmsh returned incomplete properties for element type {element_type}.")
            name = str(properties[0])
            dimension = int(properties[1])
            nodes_per_element = int(properties[3])
            tags_block = [int(value) for value in _as_list(element_tags_blocks[block_index])]
            nodes_block = [int(value) for value in _as_list(node_tags_blocks[block_index])]
            if nodes_per_element <= 0:
                raise GmshNativeError(f"Gmsh reported an invalid node count for element type {element_type}.")
            expected_connectivity = len(tags_block) * nodes_per_element
            if len(nodes_block) != expected_connectivity:
                raise GmshNativeError(
                    f"Element type {element_type} declares {len(tags_block)} elements but returned "
                    f"{len(nodes_block)} connectivity tags instead of {expected_connectivity}."
                )
            for index, element_tag in enumerate(tags_block):
                start = index * nodes_per_element
                elements.append(
                    {
                        "tag": element_tag,
                        "type": element_type,
                        "type_name": name,
                        "dimension": dimension,
                        "entity_tag": None,
                        "physical_tags": [],
                        "nodes": nodes_block[start : start + nodes_per_element],
                    }
                )

        arrays: dict[str, Any] = {}
        if node_tags:
            if len(coordinates) != len(node_tags) * 3:
                raise GmshNativeError("Gmsh node coordinates do not match the returned node-tag count.")
            arrays = _register_mesh_arrays(
                context,
                source_path=source_path,
                asset_id=asset_id,
                node_tags=node_tags,
                coordinates=coordinates,
                elements=elements,
                fields=[],
                backend_version=backend_version,
                coordinate_metadata={"reader": "gmsh-api", "mesh_generation_requested": False},
            )
            arrays.pop("field_arrays", None)

        return {
            "source_path": source_path,
            "kind": "cad_or_mesh_model",
            "status": "decoded",
            "reader": "gmsh-api",
            "mesh_generation_requested": False,
            "dimension": max((item["dimension"] for item in entities), default=None),
            "entity_count": len(entities),
            "entities": entities,
            "node_count": len(node_tags),
            "element_count": len(elements),
            "bounds": _bounds(coordinates),
            "arrays": arrays,
            "coordinate_units": "unresolved",
        }
    finally:
        if initialized:
            gmsh.finalize()
