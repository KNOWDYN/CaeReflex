"""Execution-backend discovery through an explicit entry-point group."""
from __future__ import annotations

from importlib import metadata
from typing import Any

from caereflex.contracts import ExecutionBackend
from caereflex.execution.backends import BUILTIN_BACKENDS

EXECUTION_BACKEND_GROUP = "caereflex.execution_backends"


class ExecutionBackendError(RuntimeError):
    """Raised when an execution backend cannot be resolved safely."""


def _materialise(value: Any) -> ExecutionBackend:
    backend = value() if isinstance(value, type) else value
    if not isinstance(backend, ExecutionBackend):
        raise ExecutionBackendError("Execution backend does not satisfy the required protocol.")
    return backend


def get_execution_backend(backend_id: str) -> ExecutionBackend:
    builtin = BUILTIN_BACKENDS.get(backend_id)
    if builtin is not None:
        return _materialise(builtin)

    try:
        entry_points = metadata.entry_points()
        selected = entry_points.select(group=EXECUTION_BACKEND_GROUP) if hasattr(entry_points, "select") else entry_points.get(EXECUTION_BACKEND_GROUP, [])
    except Exception as exc:
        raise ExecutionBackendError(f"Could not enumerate execution backends: {exc}") from exc

    for entry_point in selected:
        if entry_point.name != backend_id:
            continue
        try:
            return _materialise(entry_point.load())
        except Exception as exc:
            raise ExecutionBackendError(f"Could not load execution backend {backend_id!r}: {exc}") from exc
    raise ExecutionBackendError(f"Unknown execution backend: {backend_id}")


def list_execution_backends() -> list[dict[str, str]]:
    rows = [
        {"backend_id": backend_id, "backend_version": backend_class.backend_version, "source": "builtin"}
        for backend_id, backend_class in BUILTIN_BACKENDS.items()
        if not backend_id.startswith("test.")
    ]
    try:
        entry_points = metadata.entry_points()
        selected = entry_points.select(group=EXECUTION_BACKEND_GROUP) if hasattr(entry_points, "select") else entry_points.get(EXECUTION_BACKEND_GROUP, [])
        rows.extend({"backend_id": item.name, "backend_version": "unknown", "source": "entry-point"} for item in selected)
    except Exception:
        pass
    rows.sort(key=lambda item: item["backend_id"])
    return rows
