"""OpenFOAM field-cardinality and dimensional consistency rules."""
from __future__ import annotations

from caereflex.rules.context import RuleEvaluationContext
from caereflex.rules.contracts import PhysicsRuleEvaluation, RuleEvaluationStatus, RuleEvidenceRef, RuleSeverity
from caereflex.rules.openfoam_common import _COMMON_LIMITATIONS, _definition, _evaluation, _int, _source_for_field


class OpenFOAMFieldCardinalityRule:
    definition = _definition(
        "OF-CFD-FIELD-001",
        title="OpenFOAM internal-field cardinality",
        category="field_topology",
        description="Checks decoded field tuple counts and array shapes against their explicit OpenFOAM association.",
        remediation="Repair field class/internalField declarations or regenerate fields for the current mesh topology.",
        deep=True,
        severity=RuleSeverity.error,
        required=[
            ("/metadata/native_openfoam/fields", "Decoded native field inventory"),
            ("/metadata/native_openfoam/mesh", "Native mesh counts"),
        ],
    )

    def evaluate(self, context: RuleEvaluationContext) -> PhysicsRuleEvaluation:
        native = context.native_openfoam or {}
        fields = native.get("fields")
        mesh = native.get("mesh") if isinstance(native.get("mesh"), dict) else {}
        if not isinstance(fields, list) or not fields:
            return _evaluation(self.definition, RuleEvaluationStatus.unknown, "No decoded native OpenFOAM fields are available.", missing=["/metadata/native_openfoam/fields"])
        counts = {
            "vol": _int(mesh.get("cells")),
            "surface": _int(mesh.get("internal_faces")),
            "point": _int(mesh.get("points")),
        }
        evidence: list[RuleEvidenceRef] = [context.evidence("/metadata/native_openfoam/fields")]
        violations: list[str] = []
        unresolved: list[str] = []
        checked = 0
        for index, field in enumerate(fields):
            if not isinstance(field, dict):
                violations.append(f"field {index} is not an object")
                continue
            field_class = str(field.get("class") or "")
            storage = str(field.get("storage") or "")
            tuple_count = _int(field.get("tuple_count"))
            components = _int(field.get("components"))
            source = _source_for_field(field)
            if field_class.startswith("vol"):
                association = "vol"
            elif field_class.startswith("surface"):
                association = "surface"
            elif field_class.startswith("point"):
                association = "point"
            else:
                unresolved.append(source or f"field[{index}]")
                continue
            expected = counts[association]
            if expected is None:
                unresolved.append(source or f"field[{index}]")
                continue
            if storage == "unsupported" or tuple_count is None:
                unresolved.append(source or f"field[{index}]")
                continue
            checked += 1
            expected_tuples = 1 if storage == "uniform" else expected
            if tuple_count != expected_tuples:
                violations.append(f"{source or field_class}: tuple_count {tuple_count} != expected {expected_tuples}")
            array_id = field.get("array_id")
            if array_id is None:
                violations.append(f"{source or field_class}: decoded field has no ArrayRef")
                continue
            ref = context.require_array_ref(str(array_id), evidence_path=f"/metadata/native_openfoam/fields/{index}/array_id")
            expected_shape = (tuple_count, components) if components and components > 1 else (tuple_count,)
            if tuple(ref.shape) != expected_shape:
                violations.append(f"{source or field_class}: ArrayRef shape {tuple(ref.shape)} != {expected_shape}")
            evidence.append(context.evidence(f"/metadata/native_openfoam/fields/{index}", source_path=source))
        if violations:
            return _evaluation(self.definition, RuleEvaluationStatus.inconsistent, "One or more field cardinalities conflict with explicit mesh association.", evidence=evidence, details={"violations": violations, "unresolved_fields": unresolved})
        if unresolved:
            return _evaluation(self.definition, RuleEvaluationStatus.unknown, "Decoded fields checked so far are consistent, but one or more fields lack sufficient cardinality evidence.", evidence=evidence, details={"checked_fields": checked, "unresolved_fields": unresolved})
        return _evaluation(self.definition, RuleEvaluationStatus.consistent, "All decoded internal-field tuple counts and ArrayRef shapes match their explicit mesh association.", evidence=evidence, details={"checked_fields": checked})


class OpenFOAMDimensionalSemanticsRule:
    definition = _definition(
        "OF-CFD-DIMENSIONS-001",
        title="OpenFOAM declared dimensions and quantity semantics",
        category="dimensions",
        description="Checks Gate 4 dimensional-check records for explicit name/dimension conflicts.",
        remediation="Correct the declared dimensions or field/property semantics and resolve all blocked interpretations before downstream automation.",
        severity=RuleSeverity.error,
        required=[("/dimensional_checks", "Gate 4 dimensional consistency records")],
        limitations=list(_COMMON_LIMITATIONS) + ["Dimensional consistency is necessary but not sufficient for physical correctness."],
    )

    def evaluate(self, context: RuleEvaluationContext) -> PhysicsRuleEvaluation:
        checks = context.case.dimensional_checks
        if not checks:
            return _evaluation(self.definition, RuleEvaluationStatus.unknown, "No dimensional-check records are available.", missing=["/dimensional_checks"])
        conflicts: list[str] = []
        unresolved: list[str] = []
        evidence: list[RuleEvidenceRef] = []
        applicable = 0
        for index, check in enumerate(checks):
            if not isinstance(check, dict):
                continue
            status = str(check.get("status") or "")
            subject = str(check.get("subject_name") or f"check[{index}]")
            if status == "not_applicable":
                continue
            applicable += 1
            source_path = None
            paths = check.get("evidence_paths")
            if isinstance(paths, list) and paths:
                source_path = str(paths[0])
            evidence.append(context.evidence(f"/dimensional_checks/{index}", source_path=source_path))
            if status == "conflicted" or bool(check.get("blocks_automated_interpretation")):
                conflicts.append(subject)
            elif status == "unresolved":
                unresolved.append(subject)
        if conflicts:
            return _evaluation(self.definition, RuleEvaluationStatus.inconsistent, "Explicit quantity names and declared dimensions conflict.", evidence=evidence, details={"conflicted_subjects": sorted(conflicts), "unresolved_subjects": sorted(unresolved)})
        if applicable == 0:
            return _evaluation(self.definition, RuleEvaluationStatus.not_applicable, "No dimensioned CFD quantities were identified.")
        if unresolved:
            return _evaluation(self.definition, RuleEvaluationStatus.unknown, "No explicit dimensional conflict was found, but some quantity semantics remain unresolved.", evidence=evidence, details={"unresolved_subjects": sorted(unresolved)})
        return _evaluation(self.definition, RuleEvaluationStatus.consistent, "All applicable Gate 4 dimensional checks are explicitly consistent.", evidence=evidence, details={"checked_subjects": applicable})


__all__ = ["OpenFOAMFieldCardinalityRule", "OpenFOAMDimensionalSemanticsRule"]
