"""Deterministic dimensional-consistency checks with explicit unknown states."""
from __future__ import annotations

from typing import Iterable

from caereflex.contracts import (
    DiagnosticEvent,
    DiagnosticSeverity,
    DimensionalCheck,
    DimensionalConsistencyStatus,
)

from .dimensions import parse_dimension_vector, serialise_dimension_vector
from .semantics import resolve_quantity_kind


def check_dimensions(
    subject_name: str,
    vector: Iterable[float],
    *,
    context: str = "field",
    source_path: str | None = None,
) -> DimensionalCheck:
    parsed = parse_dimension_vector(vector)
    resolution = resolve_quantity_kind(subject_name, parsed, context=context)
    evidence_paths = [source_path] if source_path else []

    if resolution.status in {"name_and_dimensions", "dimensions_only"}:
        message = (
            f"{subject_name!r} is dimensionally consistent with {resolution.quantity_kind}."
            if resolution.status == "name_and_dimensions"
            else f"Dimensions identify {resolution.quantity_kind}; the source name did not provide a recognised semantic alias."
        )
        return DimensionalCheck(
            check_id="units.dimension_consistency",
            status=DimensionalConsistencyStatus.consistent,
            subject_name=subject_name,
            context=context,
            observed_dimension_vector=parsed,
            resolved_quantity_kind=resolution.quantity_kind,
            expected_quantity_kinds=list(resolution.expected_kinds),
            dimension_compatible_kinds=list(resolution.dimension_kinds),
            message=message,
            evidence_paths=evidence_paths,
        )

    if resolution.status == "conflicted":
        return DimensionalCheck(
            check_id="units.dimension_consistency",
            status=DimensionalConsistencyStatus.conflicted,
            subject_name=subject_name,
            context=context,
            observed_dimension_vector=parsed,
            expected_quantity_kinds=list(resolution.expected_kinds),
            dimension_compatible_kinds=list(resolution.dimension_kinds),
            message=(
                f"{subject_name!r} suggests {', '.join(resolution.expected_kinds)}, but its dimensions are compatible with "
                f"{', '.join(resolution.dimension_kinds) or 'no registered quantity kind'}."
            ),
            evidence_paths=evidence_paths,
            diagnostic_code="CRX-UNITS-DIMENSION-MISMATCH-001",
            blocks_automated_interpretation=True,
        )

    if resolution.status == "ambiguous":
        return DimensionalCheck(
            check_id="units.dimension_consistency",
            status=DimensionalConsistencyStatus.unresolved,
            subject_name=subject_name,
            context=context,
            observed_dimension_vector=parsed,
            expected_quantity_kinds=list(resolution.expected_kinds),
            dimension_compatible_kinds=list(resolution.dimension_kinds),
            message=(
                f"The dimensions of {subject_name!r} are compatible with multiple quantity kinds; "
                "CaeReflex will not choose one without stronger source evidence."
            ),
            evidence_paths=evidence_paths,
            diagnostic_code="CRX-UNITS-AMBIGUOUS-001",
            blocks_automated_interpretation=False,
        )

    return DimensionalCheck(
        check_id="units.dimension_consistency",
        status=DimensionalConsistencyStatus.unresolved,
        subject_name=subject_name,
        context=context,
        observed_dimension_vector=parsed,
        expected_quantity_kinds=list(resolution.expected_kinds),
        dimension_compatible_kinds=list(resolution.dimension_kinds),
        message=f"No registered quantity semantics match {subject_name!r} and {serialise_dimension_vector(parsed)}.",
        evidence_paths=evidence_paths,
        diagnostic_code="CRX-UNITS-UNRESOLVED-001",
        blocks_automated_interpretation=False,
    )


def diagnostic_from_check(check: DimensionalCheck) -> DiagnosticEvent | None:
    if not check.diagnostic_code:
        return None
    severity = DiagnosticSeverity.warning if check.status != DimensionalConsistencyStatus.consistent else DiagnosticSeverity.info
    return DiagnosticEvent(
        code=check.diagnostic_code,
        severity=severity,
        message=check.message,
        source_path=check.evidence_paths[0] if check.evidence_paths else None,
        details={
            "subject_name": check.subject_name,
            "context": check.context,
            "observed_dimension_vector": serialise_dimension_vector(check.observed_dimension_vector or (0, 0, 0, 0, 0, 0, 0)),
            "expected_quantity_kinds": check.expected_quantity_kinds,
            "dimension_compatible_kinds": check.dimension_compatible_kinds,
            "blocks_automated_interpretation": check.blocks_automated_interpretation,
        },
        parser="caereflex.units",
    )
