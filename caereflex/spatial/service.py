"""Helpers for attaching and materialising compact spatial graph references."""
from __future__ import annotations

from caereflex.contracts import InspectionExecutionResult
from caereflex.core.models import ReflexCase
from caereflex.spatial.contracts import SpatialGraphRef
from caereflex.spatial.mapping import MappingPolicy, map_execution_result
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


def map_persist_attach(
    case: ReflexCase,
    execution_result: InspectionExecutionResult | dict,
    *,
    store: SpatialStore,
    source_manifest_id: str | None = None,
    policy: MappingPolicy | None = None,
    replace: bool = False,
    require_registered_arrays: bool = True,
) -> SpatialGraphRef:
    """Map one native execution result, persist it transactionally, and attach its ref.

    Full graph and array payloads remain outside ReflexCase. Only the compact
    ``SpatialGraphRef`` is attached to additive case metadata.
    """

    snapshot = map_execution_result(
        execution_result,
        case_id=case.case_id,
        source_manifest_id=source_manifest_id,
        policy=policy,
    )
    reference = store.put_snapshot(
        snapshot,
        replace=replace,
        require_registered_arrays=require_registered_arrays,
    )
    attach_spatial_graph_ref(case, reference)
    return reference
