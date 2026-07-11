"""Helpers for attaching compact spatial graph references to ReflexCase."""
from __future__ import annotations

from caereflex.core.models import ReflexCase
from caereflex.spatial.contracts import SpatialGraphRef
from caereflex.spatial.store import SpatialStore


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
    case.spatial_graph_refs = [
        item for item in case.spatial_graph_refs if item.get("graph_id") != reference.graph_id
    ]
    case.spatial_graph_refs.append(payload)
    case.spatial_graph_refs.sort(key=lambda item: str(item.get("graph_id", "")))
    return case
