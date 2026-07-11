"""Build compact deterministic rule context from ReflexCase and execution evidence."""
from __future__ import annotations

from typing import Any


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def openfoam_rule_context(case: Any | None = None, execution_result: Any | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {"fields": [], "mesh": None, "patches": []}
    if case is not None:
        payload = _dump(case)
        if isinstance(payload, dict):
            quantity = payload.get("quantity_evidence", [])
            for item in quantity if isinstance(quantity, list) else []:
                if not isinstance(item, dict):
                    continue
                context["fields"].append({
                    "name": item.get("name") or item.get("symbol") or item.get("quantity_name"),
                    "class": item.get("field_class") or item.get("source_class"),
                    "association": item.get("association"),
                    "dimensions": item.get("dimensions") or item.get("dimension_vector"),
                    "source_path": item.get("source_path"),
                })
    if execution_result is not None:
        payload = _dump(execution_result)
        if isinstance(payload, dict):
            metadata = payload.get("metadata", {})
            backend_result = metadata.get("backend_result", {}) if isinstance(metadata, dict) else {}
            summary = backend_result.get("summary", {}) if isinstance(backend_result, dict) else {}
            if isinstance(summary, dict):
                mesh = summary.get("mesh") or summary.get("poly_mesh")
                if isinstance(mesh, dict):
                    context["mesh"] = mesh
                    patches = mesh.get("patches") or summary.get("patches")
                    if isinstance(patches, list):
                        context["patches"] = patches
                native_fields = summary.get("fields")
                if isinstance(native_fields, list):
                    by_name = {str(item.get("name") or item.get("object")): item for item in context["fields"] if isinstance(item, dict)}
                    for item in native_fields:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("name") or item.get("object") or "")
                        merged = dict(by_name.get(name, {}))
                        merged.update(item)
                        by_name[name] = merged
                    context["fields"] = [by_name[key] for key in sorted(by_name)]
    context["fields"] = sorted(
        [item for item in context["fields"] if isinstance(item, dict)],
        key=lambda item: (str(item.get("name") or item.get("object") or ""), str(item.get("source_path") or "")),
    )
    return context
