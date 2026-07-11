"""Shared definitions for the OpenFOAM CFD consistency rule pack."""
from __future__ import annotations

from typing import Any

from caereflex.rules.contracts import (
    PhysicsRuleDefinition,
    PhysicsRuleEvaluation,
    RuleApplicability,
    RuleEvaluationStatus,
    RuleEvidenceRef,
    RuleEvidenceRequirement,
    RuleSeverity,
)

OPENFOAM_CFD_PACK_ID = "openfoam.cfd-core"
OPENFOAM_CFD_PACK_VERSION = "1.0.0"

_COMMON_LIMITATIONS = [
    "This rule checks declared evidence and parser-supported structure only.",
    "It does not prove convergence, mesh independence or mesh adequacy.",
    "It does not judge turbulence-model, boundary-condition or discretisation-scheme suitability.",
    "It does not establish experimental validation, physical accuracy, certification or design safety.",
]


def _definition(
    rule_id: str,
    *,
    title: str,
    category: str,
    description: str,
    remediation: str,
    deep: bool = False,
    severity: RuleSeverity = RuleSeverity.warning,
    required: list[tuple[str, str]] | None = None,
    limitations: list[str] | None = None,
) -> PhysicsRuleDefinition:
    return PhysicsRuleDefinition(
        rule_id=rule_id,
        rule_version="1.0.0",
        pack_id=OPENFOAM_CFD_PACK_ID,
        pack_version=OPENFOAM_CFD_PACK_VERSION,
        title=title,
        category=category,
        description=description,
        severity=severity,
        applicability=RuleApplicability(
            case_types=["openfoam"],
            inspection_profiles=["deep", "forensic"] if deep else [],
            required_backends=["openfoam.native"] if deep else [],
            physics_tags=["CFD"],
        ),
        required_evidence=[
            RuleEvidenceRequirement(path=path, description=text)
            for path, text in (required or [])
        ],
        assumptions=["Only explicitly decoded and content-addressed evidence is considered."],
        remediation=remediation,
        limitations=limitations or list(_COMMON_LIMITATIONS),
    )


def _bounded_details(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "<truncated-depth>"
    if isinstance(value, list):
        preview = [_bounded_details(item, depth=depth + 1) for item in value[:64]]
        if len(value) > 64:
            return {"count": len(value), "preview": preview}
        return preview
    if isinstance(value, tuple):
        return _bounded_details(list(value), depth=depth)
    if isinstance(value, set):
        return _bounded_details(sorted(value, key=str), depth=depth)
    if isinstance(value, dict):
        keys = sorted(value, key=str)
        limited = {
            str(key): _bounded_details(value[key], depth=depth + 1)
            for key in keys[:64]
        }
        if len(keys) > 64:
            return {"count": len(keys), "preview": limited}
        return limited
    return value


def _evaluation(
    definition: PhysicsRuleDefinition,
    status: RuleEvaluationStatus,
    message: str,
    *,
    evidence: list[RuleEvidenceRef] | None = None,
    missing: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> PhysicsRuleEvaluation:
    return PhysicsRuleEvaluation(
        rule_id=definition.rule_id,
        rule_version=definition.rule_version,
        pack_id=definition.pack_id,
        pack_version=definition.pack_version,
        status=status,
        severity=definition.severity,
        message=message,
        evidence=(evidence or [])[:64],
        missing_evidence=(missing or [])[:64],
        assumptions_applied=definition.assumptions[:32],
        remediation=definition.remediation,
        limitations=definition.limitations[:32],
        details=_bounded_details(details or {}),
    )


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _source_for_field(field: dict[str, Any]) -> str | None:
    name = field.get("name")
    time = field.get("time")
    return f"{time}/{name}" if name is not None and time is not None else None


__all__ = [
    "OPENFOAM_CFD_PACK_ID",
    "OPENFOAM_CFD_PACK_VERSION",
    "_COMMON_LIMITATIONS",
    "_definition",
    "_evaluation",
    "_int",
    "_source_for_field",
]
