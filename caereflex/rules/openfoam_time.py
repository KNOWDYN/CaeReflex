"""OpenFOAM declared time-control consistency rule."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from caereflex.rules.context import RuleEvaluationContext
from caereflex.rules.contracts import PhysicsRuleEvaluation, RuleEvaluationStatus, RuleSeverity
from caereflex.rules.openfoam_common import _COMMON_LIMITATIONS, _definition, _evaluation


class OpenFOAMTimeControlsRule:
    definition = _definition(
        "OF-CFD-TIME-001",
        title="OpenFOAM declared time-control interval",
        category="solver_control",
        description="Checks explicit startTime/endTime ordering and positivity of declared deltaT/writeInterval values when numeric.",
        remediation="Correct controlDict time controls so startTime does not exceed endTime and positive intervals are used.",
        severity=RuleSeverity.warning,
        required=[("/solver_records", "Parsed controlDict solver records")],
        limitations=list(_COMMON_LIMITATIONS) + ["Time-control consistency does not demonstrate solver stability or convergence."],
    )

    def evaluate(self, context: RuleEvaluationContext) -> PhysicsRuleEvaluation:
        if not context.case.solver_records:
            return _evaluation(self.definition, RuleEvaluationStatus.not_evaluated, "No parsed controlDict solver record is available.", missing=["/solver_records"])
        record = context.case.solver_records[0].model_dump(mode="json")
        evidence = [context.evidence("/solver_records/0")]
        try:
            start = Decimal(str(record.get("start_time")))
            end = Decimal(str(record.get("end_time")))
        except (InvalidOperation, ValueError):
            return _evaluation(self.definition, RuleEvaluationStatus.unknown, "startTime or endTime is absent or non-numeric.", evidence=evidence, missing=["/solver_records/0/start_time", "/solver_records/0/end_time"])
        violations: list[str] = []
        if start > end:
            violations.append(f"startTime {start} exceeds endTime {end}")
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        checked_intervals: dict[str, str] = {}
        unresolved: list[str] = []
        for key in ("deltaT", "writeInterval"):
            if key not in metadata:
                continue
            raw = metadata[key]
            try:
                value = Decimal(str(raw))
            except (InvalidOperation, ValueError):
                unresolved.append(key)
                continue
            checked_intervals[key] = str(value)
            if value <= 0:
                violations.append(f"{key} must be positive when declared numerically")
        if violations:
            return _evaluation(self.definition, RuleEvaluationStatus.inconsistent, "Declared OpenFOAM time controls are internally inconsistent.", evidence=evidence, details={"violations": violations, "checked_intervals": checked_intervals})
        if unresolved:
            return _evaluation(self.definition, RuleEvaluationStatus.unknown, "The declared time interval is ordered, but one or more interval controls are non-numeric expressions.", evidence=evidence, details={"unresolved_controls": unresolved, "start_time": str(start), "end_time": str(end)})
        return _evaluation(self.definition, RuleEvaluationStatus.consistent, "Declared start/end times and numeric interval controls are internally consistent.", evidence=evidence, details={"start_time": str(start), "end_time": str(end), "checked_intervals": checked_intervals})


__all__ = ["OpenFOAMTimeControlsRule"]
