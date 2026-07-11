"""Helpers for attaching compact spatial graph references to ReflexCase."""
from __future__ import annotations

from caereflex.core.models import ReflexCase
from caereflex.spatial.contracts import SpatialGraphRef
from caereflex.spatial.store import SpatialStore

SPATIAL_GRAPH_REFS_KEY = "spatial_graph_refs"


def spatial_graph_refs(case: ReflexCase) -> list[dict]:
    """Return validated-looking compact references from additive case metadata."""

    value = case.metadata.get(SPATIAL_GRAPH_REFS_KEY, [])
    return list(value) if isinstance(value, list) else []


def attach_spatial_graph_ref(
    case: ReflexCase,
    graph: SpatialGraphRef | str,
    *,
    store: SpatialStore | None = None,
) -> ReflexCase:
    """Attach or replace one spatial graph reference without embedding graph payloads."""

    if isinstance(graph, str):
        if store is None:
            raise ValueError("store is required when graph is supplied as an ID")
        reference = store.graph_ref(graph)
    else:
        reference = graph

    payload = reference.model_dump(mode="json")
    references = [
        item
        for item in spatial_graph_refs(case)
        if isinstance(item, dict) and item.get("graph_id") != reference.graph_id
    ]
    references.append(payload)
    references.sort(key=lambda item: str(item.get("graph_id", "")))
    case.metadata[SPATIAL_GRAPH_REFS_KEY] = references
    return case
