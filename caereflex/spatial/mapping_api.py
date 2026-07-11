"""Public Gate 6B mapping API with compact-metadata normalisation.

Gate 6A compact metadata intentionally accepts integers but not floating-point payloads.
Native time and spacing values therefore remain evidence as canonical decimal strings when
they are copied into compact metadata. Numerical coordinates and transforms continue to
use their typed contract fields or ArrayRef payloads.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from caereflex.contracts import InspectionExecutionResult
from caereflex.spatial import mapping as _mapping
from caereflex.spatial.service import attach_spatial_graph_ref
from caereflex.spatial.store import SpatialStore


def _decimal_string(value: float) -> str:
    if not math.isfinite(value):
        raise _mapping.SpatialMappingError("Non-finite native spatial metadata is not accepted")
    return format(value, ".17g")


def _normalise_compact_native_metadata(result: InspectionExecutionResult) -> InspectionExecutionResult:
    normalised = result.model_copy(deep=True)
    for array in normalised.arrays:
        if isinstance(array.time_index, float):
            array.time_index = _decimal_string(array.time_index)

    backend_result = normalised.metadata.get("backend_result") if isinstance(normalised.metadata, dict) else None
    summary = backend_result.get("summary") if isinstance(backend_result, dict) else None
    files = summary.get("files") if isinstance(summary, dict) else None
    if isinstance(files, list):
        for file_summary in files:
            if not isinstance(file_summary, dict):
                continue
            spacing = file_summary.get("spacing")
            if isinstance(spacing, (list, tuple)):
                file_summary["spacing"] = [
                    _decimal_string(item) if isinstance(item, float) else item
                    for item in spacing
                ]
            references = file_summary.get("references")
            if isinstance(references, list):
                for reference in references:
                    if isinstance(reference, dict) and isinstance(reference.get("time"), float):
                        reference["time"] = _decimal_string(reference["time"])
    return normalised


def build_spatial_mapping(
    *,
    case_id: str,
    result: InspectionExecutionResult,
    source_manifest_id: str | None = None,
    graph_id: str | None = None,
) -> _mapping.SpatialMappingResult:
    return _mapping._build_spatial_mapping_impl(
        case_id=case_id,
        result=_normalise_compact_native_metadata(result),
        source_manifest_id=source_manifest_id,
        graph_id=graph_id,
    )


def persist_spatial_mapping(
    *,
    case: Any,
    result: InspectionExecutionResult,
    state_root: str | Path,
    source_manifest_id: str | None = None,
    graph_id: str | None = None,
) -> _mapping.SpatialMappingResult:
    mapping = build_spatial_mapping(
        case_id=str(case.case_id),
        result=result,
        source_manifest_id=source_manifest_id,
        graph_id=graph_id,
    )
    store = SpatialStore(state_root)
    reference = store.put_snapshot(
        mapping.snapshot,
        replace=True,
        require_registered_arrays=True,
    )
    attach_spatial_graph_ref(case, reference)
    reports = case.metadata.setdefault("spatial_mapping", [])
    if not isinstance(reports, list):
        reports = []
        case.metadata["spatial_mapping"] = reports
    reports[:] = [item for item in reports if item.get("graph_id") != mapping.graph_id]
    reports.append(mapping.compact_report())
    reports.sort(key=lambda item: str(item.get("graph_id", "")))
    return mapping


# Preserve an internal reference and replace both module-level public functions. Importing
# caereflex.spatial.mapping directly still passes through the package initialiser, so callers
# receive the normalised API rather than the unguarded implementation.
if not hasattr(_mapping, "_build_spatial_mapping_impl"):
    _mapping._build_spatial_mapping_impl = _mapping.build_spatial_mapping
_mapping.build_spatial_mapping = build_spatial_mapping
_mapping.persist_spatial_mapping = persist_spatial_mapping

__all__ = ["build_spatial_mapping", "persist_spatial_mapping"]
