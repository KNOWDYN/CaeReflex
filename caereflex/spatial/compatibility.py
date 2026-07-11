"""Gate 6 spatial acceptance freeze.

The freeze validates canonical graph snapshots, persisted foreign-key integrity and bounded
query responses. It does not establish geometric correctness, mesh quality, physical
validity or engineering safety.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from caereflex.contracts import CONTRACT_VERSION
from caereflex.spatial.contracts import SPATIAL_GRAPH_VERSION, SpatialGraphSnapshot
from caereflex.spatial.mapping import SPATIAL_MAPPING_VERSION
from caereflex.spatial.query import (
    SPATIAL_QUERY_VERSION,
    SpatialQueryLimits,
    SpatialQueryResult,
    SpatialQueryService,
)
from caereflex.spatial.store import SpatialStore, SpatialStoreError

GATE6_FREEZE_VERSION = "caereflex.gate6.spatial/1.0"
_SHA256_URI_RE = re.compile(r"^caereflex-artifact://sha256/[0-9a-f]{64}$")
_SHA256_CHECKSUM_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class SpatialCompatibilityIssue(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    code: str
    message: str
    path: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SpatialCompatibilityReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    freeze_version: str = GATE6_FREEZE_VERSION
    graph_id: str
    accepted: bool
    canonical_sha256: str | None = None
    graph_version: str | None = None
    contract_version: str | None = None
    mapping_version: str | None = None
    query_version: str = SPATIAL_QUERY_VERSION
    frame_count: int = 0
    entity_count: int = 0
    relation_count: int = 0
    array_link_count: int = 0
    errors: list[SpatialCompatibilityIssue] = Field(default_factory=list)
    warnings: list[SpatialCompatibilityIssue] = Field(default_factory=list)
    checks: dict[str, bool] = Field(default_factory=dict)


class SpatialCompatibilityError(RuntimeError):
    """Raised when a Gate 6 acceptance operation cannot be executed."""


def _canonical_payload(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SpatialCompatibilityError(f"spatial payload is not strict JSON: {exc}") from exc


def _sorted_ids(items: Iterable[Any], attribute: str) -> bool:
    values = [str(getattr(item, attribute)) for item in items]
    return values == sorted(values)


def _issue(code: str, message: str, path: str | None = None, **details: Any) -> SpatialCompatibilityIssue:
    return SpatialCompatibilityIssue(code=code, message=message, path=path, details=details)


def validate_spatial_snapshot(
    snapshot: SpatialGraphSnapshot,
    *,
    registered_array_ids: set[str] | None = None,
) -> SpatialCompatibilityReport:
    """Validate one complete snapshot against the frozen Gate 6 contract."""

    snapshot = SpatialGraphSnapshot.model_validate(snapshot.model_dump(mode="json"))
    graph = snapshot.graph
    errors: list[SpatialCompatibilityIssue] = []
    warnings: list[SpatialCompatibilityIssue] = []
    checks: dict[str, bool] = {}

    checks["graph_version"] = graph.graph_version == SPATIAL_GRAPH_VERSION
    if not checks["graph_version"]:
        errors.append(_issue(
            "CRX-GATE6-COMPAT-001", "Spatial graph version is outside the frozen Gate 6 contract.",
            "graph.graph_version", expected=SPATIAL_GRAPH_VERSION, actual=graph.graph_version,
        ))
    checks["contract_version"] = graph.contract_version == CONTRACT_VERSION
    if not checks["contract_version"]:
        errors.append(_issue(
            "CRX-GATE6-COMPAT-001", "Spatial graph contract version does not match the runtime contract.",
            "graph.contract_version", expected=CONTRACT_VERSION, actual=graph.contract_version,
        ))

    mapping_version = graph.metadata.get("mapping_version") if isinstance(graph.metadata, dict) else None
    checks["mapping_version"] = mapping_version in {None, SPATIAL_MAPPING_VERSION}
    if not checks["mapping_version"]:
        errors.append(_issue(
            "CRX-GATE6-COMPAT-001", "Mapped graph uses an unsupported spatial mapping version.",
            "graph.metadata.mapping_version", expected=SPATIAL_MAPPING_VERSION, actual=mapping_version,
        ))
    cross_format = bool(graph.metadata.get("cross_format_equivalence_asserted", False))
    checks["cross_format_equivalence_not_asserted"] = not cross_format
    if cross_format:
        errors.append(_issue(
            "CRX-GATE6-COMPAT-001", "Gate 6 freeze does not permit an automated cross-format equivalence assertion.",
            "graph.metadata.cross_format_equivalence_asserted",
        ))

    ordering_checks = {
        "frames_ordered": _sorted_ids(snapshot.coordinate_frames, "frame_id"),
        "entities_ordered": _sorted_ids(snapshot.entities, "entity_id"),
        "relations_ordered": _sorted_ids(snapshot.relations, "relation_id"),
        "array_links_ordered": _sorted_ids(snapshot.array_links, "link_id"),
    }
    checks.update(ordering_checks)
    for label, passed in ordering_checks.items():
        if not passed:
            errors.append(_issue(
                "CRX-GATE6-COMPAT-001", "Spatial snapshot collections must use deterministic identifier ordering.", label,
            ))

    array_links_valid = True
    for index, link in enumerate(snapshot.array_links):
        path = f"array_links[{index}]"
        if link.array_uri is None or _SHA256_URI_RE.fullmatch(link.array_uri) is None:
            array_links_valid = False
            errors.append(_issue(
                "CRX-GATE6-COMPAT-001", "Spatial array links must use SHA-256 content-addressed artefact URIs.",
                f"{path}.array_uri", array_uri=link.array_uri,
            ))
        if link.checksum is None or _SHA256_CHECKSUM_RE.fullmatch(link.checksum) is None:
            array_links_valid = False
            errors.append(_issue(
                "CRX-GATE6-COMPAT-001", "Spatial array links must retain a SHA-256 checksum.",
                f"{path}.checksum", checksum=link.checksum,
            ))
        if registered_array_ids is not None and link.array_id not in registered_array_ids:
            array_links_valid = False
            errors.append(_issue(
                "CRX-GATE6-COMPAT-001", "Spatial array link references an ArrayRef absent from the shared registry.",
                f"{path}.array_id", array_id=link.array_id,
            ))
    checks["array_links_content_addressed"] = array_links_valid

    try:
        canonical = _canonical_payload(snapshot.model_dump(mode="json"))
        canonical_sha256 = hashlib.sha256(canonical).hexdigest()
        checks["strict_json"] = True
    except SpatialCompatibilityError as exc:
        canonical_sha256 = None
        checks["strict_json"] = False
        errors.append(_issue("CRX-GATE6-COMPAT-001", str(exc), "snapshot"))
    if mapping_version == SPATIAL_MAPPING_VERSION and "cross_format_equivalence_asserted" not in graph.metadata:
        warnings.append(_issue(
            "CRX-GATE6-COMPAT-001", "Mapped graph omits the explicit cross-format non-equivalence marker.",
            "graph.metadata.cross_format_equivalence_asserted",
        ))

    return SpatialCompatibilityReport(
        graph_id=graph.graph_id, accepted=not errors, canonical_sha256=canonical_sha256,
        graph_version=graph.graph_version, contract_version=graph.contract_version,
        mapping_version=str(mapping_version) if mapping_version is not None else None,
        frame_count=len(snapshot.coordinate_frames), entity_count=len(snapshot.entities),
        relation_count=len(snapshot.relations), array_link_count=len(snapshot.array_links),
        errors=errors, warnings=warnings, checks=checks,
    )


def validate_spatial_query_result(
    result: SpatialQueryResult, *, limits: SpatialQueryLimits | None = None,
) -> list[SpatialCompatibilityIssue]:
    policy = limits or SpatialQueryLimits()
    issues: list[SpatialCompatibilityIssue] = []
    if result.query_version != SPATIAL_QUERY_VERSION:
        issues.append(_issue(
            "CRX-GATE6-COMPAT-001", "Spatial query result version is outside the frozen Gate 6 contract.",
            "query_version", expected=SPATIAL_QUERY_VERSION, actual=result.query_version,
        ))
    for label, items, attr in (
        ("graphs", result.graphs, "graph_id"), ("frames", result.frames, "frame_id"),
        ("relations", result.relations, "relation_id"), ("array_links", result.array_links, "link_id"),
    ):
        if len(items) > policy.max_results:
            issues.append(_issue(
                "CRX-GATE6-COMPAT-001", f"Spatial query returned too many {label}.", label,
                maximum=policy.max_results, actual=len(items),
            ))
        if not _sorted_ids(items, attr):
            issues.append(_issue(
                "CRX-GATE6-COMPAT-001", f"Spatial query {label} are not deterministically ordered.", label,
            ))
    if len(result.entities) > policy.max_results:
        issues.append(_issue(
            "CRX-GATE6-COMPAT-001", "Spatial query returned too many entities.", "entities",
            maximum=policy.max_results, actual=len(result.entities),
        ))
    if result.operation != "neighbours" and not _sorted_ids(result.entities, "entity_id"):
        issues.append(_issue(
            "CRX-GATE6-COMPAT-001", "Spatial query entities are not deterministically ordered.", "entities",
        ))
    if result.scanned_count < 0 or result.returned_count < 0:
        issues.append(_issue("CRX-GATE6-COMPAT-001", "Spatial query counts cannot be negative.", "counts"))
    try:
        payload = _canonical_payload(result.model_dump(mode="json"))
        if len(payload) > policy.max_serialized_bytes:
            issues.append(_issue(
                "CRX-GATE6-COMPAT-001", "Spatial query response exceeds the frozen serialized-size limit.",
                "result", maximum=policy.max_serialized_bytes, actual=len(payload),
            ))
    except SpatialCompatibilityError as exc:
        issues.append(_issue("CRX-GATE6-COMPAT-001", str(exc), "result"))
    return issues


def _registered_arrays(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path, timeout=30.0) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'array_refs'"
        ).fetchone()
        if table is None:
            return set()
        return {str(row[0]) for row in connection.execute("SELECT array_id FROM array_refs")}


def validate_spatial_store(
    state_root: str | Path, graph_id: str, *, query_limits: SpatialQueryLimits | None = None,
) -> SpatialCompatibilityReport:
    store = SpatialStore(state_root)
    try:
        snapshot = store.snapshot(graph_id)
    except (SpatialStoreError, ValueError) as exc:
        raise SpatialCompatibilityError(str(exc)) from exc
    report = validate_spatial_snapshot(snapshot, registered_array_ids=_registered_arrays(store.database_path))
    integrity = store.validate_integrity()
    report.checks["sqlite_foreign_keys"] = not integrity
    if integrity:
        report.errors.append(_issue(
            "CRX-GATE6-COMPAT-001", "Spatial store foreign-key integrity check failed.", "sqlite",
            violations=integrity,
        ))
    policy = query_limits or SpatialQueryLimits()
    service = SpatialQueryService(state_root, limits=policy)
    smoke_results = [
        service.describe_graph(graph_id), service.query_frames(graph_id, limit=1),
        service.query_entities(graph_id, limit=1), service.query_relations(graph_id, limit=1),
        service.query_array_links(graph_id, limit=1),
    ]
    query_issues: list[SpatialCompatibilityIssue] = []
    for result in smoke_results:
        query_issues.extend(validate_spatial_query_result(result, limits=policy))
    report.checks["bounded_query_surface"] = not query_issues
    report.errors.extend(query_issues)
    report.accepted = not report.errors
    return report


__all__ = [
    "GATE6_FREEZE_VERSION", "SpatialCompatibilityError", "SpatialCompatibilityIssue",
    "SpatialCompatibilityReport", "validate_spatial_query_result", "validate_spatial_snapshot",
    "validate_spatial_store",
]
