"""Frozen Gate 5 execution-backend result envelope.

Backend-specific evidence remains under ``summary``. This module stamps every
built-in Gate 5 backend with one small common report and rejects payload drift
before the worker persists a result.
"""
from __future__ import annotations

import math
import re
from pathlib import PurePosixPath
from typing import Any

from caereflex.contracts import InspectionExecutionRequest
from caereflex.execution.context import ExecutionContext

GATE5_BACKEND_CONTRACT = "caereflex.gate5.backend-result/1.0"
FROZEN_BUILTIN_BACKENDS = frozenset(
    {
        "core.manifest-audit",
        "openfoam.native",
        "gmsh.native",
        "vtk.native",
    }
)
_MAX_NESTING_DEPTH = 24
_MAX_SEQUENCE_ITEMS = 100_000
_MAX_INLINE_HEAVY_ITEMS = 256
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_HEAVY_KEYS = {
    "values",
    "coordinates",
    "connectivity",
    "node_values",
    "cell_values",
    "field_values",
    "point_values",
    "face_values",
    "element_values",
}


class BackendCompatibilityError(RuntimeError):
    """Raised when a backend violates the frozen Gate 5 result contract."""


def _unsafe_path(value: str) -> bool:
    path = PurePosixPath(value.replace("\\", "/"))
    return path.is_absolute() or ".." in path.parts or bool(_WINDOWS_ABSOLUTE_RE.match(value))


def _validate_json_tree(value: Any, *, path: str = "$", depth: int = 0) -> None:
    if depth > _MAX_NESTING_DEPTH:
        raise BackendCompatibilityError(
            f"Backend result exceeds the maximum nesting depth at {path}."
        )
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BackendCompatibilityError(
                f"Backend result contains a non-finite floating-point value at {path}."
            )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise BackendCompatibilityError(
                    f"Backend result contains a non-string mapping key at {path}."
                )
            child_path = f"{path}.{key}"
            if key == "source_path" or key.endswith("_path"):
                if isinstance(item, str) and _unsafe_path(item):
                    raise BackendCompatibilityError(
                        f"Backend result exposes an unsafe or absolute source path at {child_path}."
                    )
            if key in _HEAVY_KEYS and isinstance(item, (list, tuple)) and len(item) > _MAX_INLINE_HEAVY_ITEMS:
                raise BackendCompatibilityError(
                    f"Backend result materialises heavy numerical data at {child_path}; use ArrayRef."
                )
            _validate_json_tree(item, path=child_path, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_SEQUENCE_ITEMS:
            raise BackendCompatibilityError(
                f"Backend result contains an oversized sequence at {path}."
            )
        for index, item in enumerate(value):
            _validate_json_tree(item, path=f"{path}[{index}]", depth=depth + 1)
        return
    raise BackendCompatibilityError(
        f"Backend result contains a non-JSON value of type {type(value).__name__} at {path}."
    )


def _evidence_status(backend_id: str, context: ExecutionContext) -> str:
    failed = any(str(item.outcome) in {"failed", "timed_out", "crashed"} for item in context.attempts)
    if backend_id == "core.manifest-audit":
        return "metadata_only"
    if context.arrays and failed:
        return "partially_decoded"
    if context.arrays:
        return "decoded"
    if failed:
        return "fallback_only"
    return "metadata_only"


def freeze_backend_payload(
    payload: Any,
    *,
    request: InspectionExecutionRequest,
    context: ExecutionContext,
    backend_version: str | None,
) -> dict[str, Any]:
    """Validate and stamp a backend payload with the frozen Gate 5 envelope."""

    if not isinstance(payload, dict):
        raise BackendCompatibilityError("Execution backends must return a JSON object.")
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise BackendCompatibilityError(
            "Execution backends must return a JSON object containing a summary object."
        )

    expected_array_count = len(context.arrays)
    expected_artifact_count = len(context.artifacts)
    expected_diagnostic_count = len(context.diagnostics)

    declared_array_count = summary.get("array_count")
    if declared_array_count is not None and declared_array_count != expected_array_count:
        raise BackendCompatibilityError(
            "Backend summary array_count does not match registered ArrayRef objects."
        )
    declared_diagnostic_count = summary.get("diagnostic_count")
    if declared_diagnostic_count is not None and declared_diagnostic_count != expected_diagnostic_count:
        raise BackendCompatibilityError(
            "Backend summary diagnostic_count does not match emitted diagnostics."
        )

    for ref in context.arrays:
        if not ref.array_id:
            raise BackendCompatibilityError("Every Gate 5 ArrayRef must have a stable array_id.")
        if not ref.uri.startswith("caereflex-artifact://sha256/"):
            raise BackendCompatibilityError(
                f"ArrayRef {ref.array_id} does not use the content-addressed artefact URI."
            )
        if ref.backend != request.backend_id:
            raise BackendCompatibilityError(
                f"ArrayRef {ref.array_id} backend identity does not match the executing backend."
            )
        if ref.source_path and _unsafe_path(ref.source_path):
            raise BackendCompatibilityError(
                f"ArrayRef {ref.array_id} exposes an unsafe or absolute source path."
            )

    for artifact in context.artifacts:
        if not artifact.uri.startswith("caereflex-artifact://sha256/"):
            raise BackendCompatibilityError(
                f"Artefact {artifact.artifact_id} does not use the content-addressed artefact URI."
            )

    for accessed in context.paths_accessed:
        if _unsafe_path(accessed):
            raise BackendCompatibilityError(
                "Execution context recorded an unsafe or absolute accessed path."
            )

    profile = getattr(request.plan.profile, "value", str(request.plan.profile))
    parser_attempt_count = len(context.attempts) if context.attempts else 1
    summary.setdefault("reader", request.backend_id)
    summary.setdefault("format", request.plan.plugin_id)
    summary.setdefault("array_count", expected_array_count)
    summary.setdefault("diagnostic_count", expected_diagnostic_count)
    summary["gate5_compatibility"] = {
        "contract": GATE5_BACKEND_CONTRACT,
        "frozen": request.backend_id in FROZEN_BUILTIN_BACKENDS,
        "backend_id": request.backend_id,
        "backend_version": backend_version,
        "plugin_id": request.plan.plugin_id,
        "profile": profile,
        "read_only": True,
        "source_execution": False,
        "heavy_arrays_externalised": True,
        "source_paths_relative": True,
        "evidence_status": _evidence_status(request.backend_id, context),
        "array_count": expected_array_count,
        "artifact_count": expected_artifact_count,
        "diagnostic_count": expected_diagnostic_count,
        "parser_attempt_count": parser_attempt_count,
    }

    _validate_json_tree(payload)
    return payload


__all__ = [
    "BackendCompatibilityError",
    "FROZEN_BUILTIN_BACKENDS",
    "GATE5_BACKEND_CONTRACT",
    "freeze_backend_payload",
]
