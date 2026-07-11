"""Deterministic physics-consistency rule engine and pack registry."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from caereflex.core.models import ReflexCase
from caereflex.rules.context import RuleEvaluationContext
from caereflex.rules.contracts import (
    RULE_PROTOCOL_VERSION,
    PhysicsRule,
    PhysicsRuleEvaluation,
    PhysicsRulePackManifest,
    PhysicsRuleRunReport,
    RuleBlockedError,
    RuleEvaluationStatus,
    RulePackNotFoundError,
    RuleRunStatus,
)


class RegisteredRulePack:
    def __init__(self, manifest: PhysicsRulePackManifest, rules: Iterable[PhysicsRule]) -> None:
        ordered = sorted(rules, key=lambda item: item.definition.rule_id)
        ids = [item.definition.rule_id for item in ordered]
        if ids != manifest.rule_ids:
            raise ValueError("rule pack manifest rule_ids must match deterministic rule ordering")
        for rule in ordered:
            definition = rule.definition
            if definition.pack_id != manifest.pack_id or definition.pack_version != manifest.pack_version:
                raise ValueError("rule definition pack identity does not match the manifest")
        self.manifest = manifest
        self.rules = tuple(ordered)


_PACKS: dict[str, RegisteredRulePack] = {}


def register_rule_pack(pack: RegisteredRulePack, *, replace: bool = False) -> RegisteredRulePack:
    if pack.manifest.protocol_version != RULE_PROTOCOL_VERSION:
        raise ValueError("rule pack protocol version is incompatible with this runtime")
    if pack.manifest.pack_id in _PACKS and not replace:
        raise ValueError(f"rule pack already registered: {pack.manifest.pack_id}")
    _PACKS[pack.manifest.pack_id] = pack
    return pack


def get_rule_pack(pack_id: str) -> RegisteredRulePack:
    try:
        return _PACKS[pack_id]
    except KeyError as exc:
        raise RulePackNotFoundError(f"Unknown physics rule pack: {pack_id}") from exc


def list_rule_packs() -> list[PhysicsRulePackManifest]:
    return [_PACKS[key].manifest for key in sorted(_PACKS)]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _input_payload(case: ReflexCase) -> dict[str, Any]:
    payload = copy.deepcopy(case.model_dump(mode="json"))
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("physics_consistency", None)
    provenance = payload.get("provenance")
    if isinstance(provenance, list):
        payload["provenance"] = [
            item for item in provenance
            if not (isinstance(item, dict) and item.get("event") == "physics_consistency_rules_evaluated")
        ]
    flags = payload.get("inspection_flags")
    if isinstance(flags, list):
        payload["inspection_flags"] = [
            item for item in flags
            if not (isinstance(item, dict) and str(item.get("category", "")).startswith("physics_consistency_"))
        ]
    agent_summary = payload.get("agent_summary")
    if isinstance(agent_summary, dict):
        agent_summary["do_not_claim"] = []
    return payload


def _result(
    rule: PhysicsRule,
    status: RuleEvaluationStatus,
    message: str,
    *,
    evidence: list[Any] | None = None,
    missing_evidence: list[str] | None = None,
    assumptions_applied: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> PhysicsRuleEvaluation:
    definition = rule.definition
    return PhysicsRuleEvaluation(
        rule_id=definition.rule_id,
        rule_version=definition.rule_version,
        pack_id=definition.pack_id,
        pack_version=definition.pack_version,
        status=status,
        severity=definition.severity,
        message=message,
        evidence=evidence or [],
        missing_evidence=missing_evidence or [],
        assumptions_applied=assumptions_applied or [],
        remediation=definition.remediation,
        limitations=definition.limitations,
        details=details or {},
    )


def _applicability_result(rule: PhysicsRule, context: RuleEvaluationContext) -> PhysicsRuleEvaluation | None:
    definition = rule.definition
    applicability = definition.applicability
    case_type = str(context.case.case_type)
    if applicability.case_types and case_type not in applicability.case_types:
        return _result(
            rule,
            RuleEvaluationStatus.not_applicable,
            f"Rule does not apply to case type {case_type!r}.",
            details={"case_type": case_type},
        )

    profile = context.case.inspection_profile
    if applicability.inspection_profiles and profile not in applicability.inspection_profiles:
        return _result(
            rule,
            RuleEvaluationStatus.not_evaluated,
            "Rule requires a deeper inspection profile than the available ReflexCase.",
            missing_evidence=["/inspection_profile"],
            details={"required_profiles": applicability.inspection_profiles, "actual_profile": profile},
        )

    if applicability.required_backends:
        execution = context.resolve("/metadata/inspection_execution", None)
        backend = execution.get("backend_id") if isinstance(execution, dict) else None
        if backend not in applicability.required_backends:
            return _result(
                rule,
                RuleEvaluationStatus.not_evaluated,
                "Rule requires native backend evidence that is not attached to this ReflexCase.",
                missing_evidence=["/metadata/inspection_execution/backend_id"],
                details={"required_backends": applicability.required_backends, "actual_backend": backend},
            )

    missing_required = [
        item.path for item in definition.required_evidence
        if item.required and not context.exists(item.path)
    ]
    if missing_required:
        return _result(
            rule,
            RuleEvaluationStatus.not_evaluated,
            "Required evidence paths are absent from this ReflexCase.",
            missing_evidence=missing_required,
        )

    if applicability.physics_tags:
        available = {str(item).lower() for item in context.case.physics_tags}
        required = {str(item).lower() for item in applicability.physics_tags}
        if not required.intersection(available):
            return _result(
                rule,
                RuleEvaluationStatus.not_applicable,
                "Rule pack domain tags do not match the inspected case.",
                details={"required_tags": applicability.physics_tags, "available_tags": sorted(available)},
            )
    return None


def evaluate_rule_pack(
    case: ReflexCase,
    *,
    pack_id: str,
    state_root: str | Path | None = None,
) -> PhysicsRuleRunReport:
    pack = get_rule_pack(pack_id)
    context = RuleEvaluationContext(case, state_root=state_root)
    input_sha = hashlib.sha256(_canonical_bytes(_input_payload(case))).hexdigest()
    results: list[PhysicsRuleEvaluation] = []

    for rule in pack.rules:
        precomputed = _applicability_result(rule, context)
        if precomputed is not None:
            results.append(precomputed)
            continue
        try:
            evaluation = rule.evaluate(context)
        except RuleBlockedError as exc:
            evaluation = _result(
                rule,
                RuleEvaluationStatus.blocked,
                str(exc),
                details={"blocked_reason": str(exc)},
            )
        except Exception as exc:  # defensive boundary for third-party rule packs
            evaluation = _result(
                rule,
                RuleEvaluationStatus.blocked,
                f"Rule evaluation failed deterministically: {type(exc).__name__}: {exc}",
                details={"exception_type": type(exc).__name__},
            )
        if evaluation.rule_id != rule.definition.rule_id or evaluation.rule_version != rule.definition.rule_version:
            raise ValueError("rule returned an evaluation with a mismatched identity")
        results.append(evaluation)

    counts = {status.value: 0 for status in RuleEvaluationStatus}
    for item in results:
        value = item.status.value if hasattr(item.status, "value") else str(item.status)
        counts[value] += 1

    if counts[RuleEvaluationStatus.blocked.value]:
        status = RuleRunStatus.blocked
    elif counts[RuleEvaluationStatus.inconsistent.value]:
        status = RuleRunStatus.inconsistent
    elif counts[RuleEvaluationStatus.unknown.value] or counts[RuleEvaluationStatus.not_evaluated.value]:
        status = RuleRunStatus.incomplete
    elif results and counts[RuleEvaluationStatus.not_applicable.value] == len(results):
        status = RuleRunStatus.not_applicable
    else:
        status = RuleRunStatus.consistent

    run_seed = f"{case.case_id}\x1f{pack.manifest.pack_id}\x1f{pack.manifest.pack_version}\x1f{input_sha}"
    run_id = "rule_run_" + hashlib.sha256(run_seed.encode("utf-8")).hexdigest()[:24]
    report = PhysicsRuleRunReport(
        pack_id=pack.manifest.pack_id,
        pack_version=pack.manifest.pack_version,
        case_id=case.case_id,
        run_id=run_id,
        input_sha256=input_sha,
        status=status,
        results=results,
        counts=counts,
        limitations=pack.manifest.limitations,
    )
    canonical = report.model_dump(mode="json", exclude={"canonical_sha256"})
    report.canonical_sha256 = hashlib.sha256(_canonical_bytes(canonical)).hexdigest()
    return report


__all__ = [
    "RegisteredRulePack",
    "evaluate_rule_pack",
    "get_rule_pack",
    "list_rule_packs",
    "register_rule_pack",
]
