"""Deterministic, fail-closed physics-consistency rule engine."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from caereflex.physics.contracts import (
    RuleDefinition,
    RuleEvaluationReport,
    RulePackManifest,
    RuleResult,
    RuleSeverity,
    RuleStatus,
)

RuleEvaluator = Callable[[dict[str, Any], RuleDefinition], RuleResult]


@dataclass(frozen=True)
class RegisteredRule:
    definition: RuleDefinition
    evaluator: RuleEvaluator


class PhysicsRuleEngine:
    def __init__(self, pack: RulePackManifest, rules: Iterable[RegisteredRule]) -> None:
        ordered = sorted(rules, key=lambda item: item.definition.rule_id)
        ids = [item.definition.rule_id for item in ordered]
        if ids != sorted(pack.rule_ids) or len(ids) != len(set(ids)):
            raise ValueError("rule pack manifest and registered rule IDs must match exactly")
        self.pack = pack
        self.rules = ordered

    @staticmethod
    def _input_digest(context: dict[str, Any]) -> str:
        payload = json.dumps(context, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def evaluate(self, context: dict[str, Any], *, case_id: str | None = None, backend_id: str | None = None) -> RuleEvaluationReport:
        results: list[RuleResult] = []
        for item in self.rules:
            try:
                result = item.evaluator(context, item.definition)
                if result.rule_id != item.definition.rule_id or result.rule_version != item.definition.version:
                    raise ValueError("evaluator returned a mismatched rule identity")
            except Exception as exc:  # deterministic fail-closed boundary
                result = RuleResult(
                    rule_id=item.definition.rule_id,
                    rule_version=item.definition.version,
                    status=RuleStatus.blocked,
                    severity=RuleSeverity.error,
                    message=f"Rule evaluation was blocked by an internal contract error: {type(exc).__name__}",
                    missing_evidence=[],
                    assumptions=item.definition.assumptions,
                    remediation="Inspect the rule implementation and preserved input evidence before retrying.",
                    limitation=item.definition.limitation,
                )
            results.append(result)
        summary = {status.value: 0 for status in RuleStatus}
        for result in results:
            summary[str(result.status)] += 1
        report = RuleEvaluationReport(
            pack=self.pack,
            case_id=case_id,
            backend_id=backend_id,
            results=results,
            summary=summary,
            input_digest=self._input_digest(context),
        )
        return report.with_digest()
