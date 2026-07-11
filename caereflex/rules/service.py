"""Application service for evaluating and attaching physics-consistency reports."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from caereflex.core.models import InspectionFlag, ProvenanceRecord, ReflexCase, Severity
from caereflex.rules.engine import evaluate_rule_pack


def _status_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def evaluate_case_rules(
    case: ReflexCase,
    *,
    pack_id: str = "openfoam.cfd-core",
    state_root: str | Path | None = None,
    attach: bool = True,
):
    report = evaluate_rule_pack(case, pack_id=pack_id, state_root=state_root)
    if not attach:
        return report

    root = case.metadata.setdefault("physics_consistency", {})
    if not isinstance(root, dict):
        root = {}
        case.metadata["physics_consistency"] = root
    root["protocol_version"] = report.protocol_version
    runs = root.setdefault("runs", [])
    if not isinstance(runs, list):
        runs = []
        root["runs"] = runs
    payload = report.model_dump(mode="json")
    runs[:] = [
        item for item in runs
        if not (
            isinstance(item, dict)
            and item.get("pack_id") == report.pack_id
            and item.get("pack_version") == report.pack_version
        )
    ]
    runs.append(payload)
    runs.sort(key=lambda item: (str(item.get("pack_id", "")), str(item.get("pack_version", ""))))

    case.provenance.append(
        ProvenanceRecord(
            event="physics_consistency_rules_evaluated",
            details={
                "protocol_version": report.protocol_version,
                "pack_id": report.pack_id,
                "pack_version": report.pack_version,
                "run_id": report.run_id,
                "status": report.status,
                "canonical_sha256": report.canonical_sha256,
            },
        )
    )
    category = None
    message = None
    status = _status_value(report.status)
    if status == "inconsistent":
        category = "physics_consistency_inconsistent"
        message = "Deterministic physics-consistency rules found one or more explicit evidence conflicts."
    elif status == "blocked":
        category = "physics_consistency_blocked"
        message = "One or more physics-consistency rules were blocked by inaccessible or untrusted evidence."
    elif status == "incomplete":
        category = "physics_consistency_incomplete"
        message = "Physics-consistency evaluation completed with unknown or unevaluated rules."
    case.inspection_flags[:] = [
        item for item in case.inspection_flags
        if not str(item.category).startswith("physics_consistency_")
    ]
    if category and message:
        case.inspection_flags.append(
            InspectionFlag(severity=Severity.warning, category=category, message=message)
        )

    for limitation in report.limitations:
        if limitation not in case.agent_summary.do_not_claim:
            case.agent_summary.do_not_claim.append(limitation)
    return report


def physics_consistency_runs(case: ReflexCase) -> list[dict[str, Any]]:
    root = case.metadata.get("physics_consistency")
    if not isinstance(root, dict):
        return []
    runs = root.get("runs")
    return [item for item in runs if isinstance(item, dict)] if isinstance(runs, list) else []


__all__ = ["evaluate_case_rules", "physics_consistency_runs"]
