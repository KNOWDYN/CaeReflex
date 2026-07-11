"""Deterministic bounded structural comparisons between immutable revisions."""
from __future__ import annotations

import uuid
from typing import Any

from caereflex.lifecycle.contracts import (
    TEMPORAL_COMPARISON_PROTOCOL_VERSION,
    ChangeKind,
    TemporalChange,
    TemporalComparison,
    canonical_digest,
)
from caereflex.lifecycle.store import LifecycleStore, LifecycleStoreError

DEFAULT_IGNORED_PATHS = [
    "/created_at",
    "/updated_at",
    "/inspection/started_at",
    "/inspection/completed_at",
    "/provenance/*/timestamp",
    "/exports/*/created_at",
]


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _flatten(value: Any, path: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        if not value:
            return {path or "/": {}}
        result: dict[str, Any] = {}
        for key in sorted(value):
            result.update(_flatten(value[key], f"{path}/{_escape(str(key))}"))
        return result
    if isinstance(value, list):
        if not value:
            return {path or "/": []}
        result: dict[str, Any] = {}
        for index, item in enumerate(value):
            result.update(_flatten(item, f"{path}/{index}"))
        return result
    return {path or "/": value}


def _matches(path: str, pattern: str) -> bool:
    path_parts = path.strip("/").split("/") if path != "/" else []
    pattern_parts = pattern.strip("/").split("/") if pattern != "/" else []
    if len(path_parts) < len(pattern_parts):
        return False
    for actual, expected in zip(path_parts, pattern_parts):
        if expected != "*" and actual != expected:
            return False
    return True


def _bounded_value(value: Any, maximum: int = 512) -> Any:
    if isinstance(value, str) and len(value) > maximum:
        return value[:maximum] + f"… [{len(value) - maximum} characters omitted]"
    return value


def compare_revisions(
    store: LifecycleStore,
    project_id: str,
    baseline_revision_id: str,
    candidate_revision_id: str,
    *,
    ignore_paths: list[str] | None = None,
    max_changes: int = 200,
    persist: bool = True,
) -> TemporalComparison:
    if max_changes < 1 or max_changes > 500:
        raise LifecycleStoreError("max_changes must be between 1 and 500")
    baseline_record = store.get_revision(baseline_revision_id)
    candidate_record = store.get_revision(candidate_revision_id)
    if baseline_record.project_id != project_id or candidate_record.project_id != project_id:
        raise LifecycleStoreError("both revisions must belong to the requested project")
    ignored = list(dict.fromkeys(DEFAULT_IGNORED_PATHS + (ignore_paths or [])))
    baseline = {
        path: value
        for path, value in _flatten(store.load_revision_payload(baseline_revision_id)).items()
        if not any(_matches(path, pattern) for pattern in ignored)
    }
    candidate = {
        path: value
        for path, value in _flatten(store.load_revision_payload(candidate_revision_id)).items()
        if not any(_matches(path, pattern) for pattern in ignored)
    }
    all_paths = sorted(set(baseline) | set(candidate))
    changes: list[TemporalChange] = []
    counts = {kind.value: 0 for kind in ChangeKind}
    for path in all_paths:
        if path not in baseline:
            kind = ChangeKind.added
            before, after = None, candidate[path]
        elif path not in candidate:
            kind = ChangeKind.removed
            before, after = baseline[path], None
        elif baseline[path] != candidate[path]:
            kind = ChangeKind.changed
            before, after = baseline[path], candidate[path]
        else:
            continue
        counts[kind.value] += 1
        if len(changes) < max_changes:
            changes.append(
                TemporalChange(
                    path=path,
                    kind=kind,
                    before=_bounded_value(before),
                    after=_bounded_value(after),
                )
            )
    total = sum(counts.values())
    truncated = total > len(changes)
    comparison_digest = canonical_digest(
        {
            "protocol_version": TEMPORAL_COMPARISON_PROTOCOL_VERSION,
            "project_id": project_id,
            "baseline_revision_id": baseline_revision_id,
            "candidate_revision_id": candidate_revision_id,
            "baseline_digest": baseline_record.case_digest,
            "candidate_digest": candidate_record.case_digest,
            "ignored_paths": ignored,
            "counts": counts,
            "changes": [item.model_dump(mode="json") for item in changes],
            "truncated": truncated,
        }
    )
    comparison = TemporalComparison(
        comparison_id=f"comparison_{uuid.uuid4().hex[:16]}",
        project_id=project_id,
        baseline_revision_id=baseline_revision_id,
        candidate_revision_id=candidate_revision_id,
        baseline_digest=baseline_record.case_digest,
        candidate_digest=candidate_record.case_digest,
        ignored_paths=ignored,
        counts=counts,
        changes=changes,
        truncated=truncated,
        comparison_digest=comparison_digest,
    )
    return store.save_comparison(comparison) if persist else comparison
