"""OpenFOAM-specific dimensional evidence bridge.

This module parses dimensions and scalar values only. It does not execute includes,
macros, coded boundary conditions, or solver dictionaries.
"""
from __future__ import annotations

import re
from typing import Any

from caereflex.contracts import EvidenceState, QuantityEvidence, SourceLocation

from .checks import check_dimensions
from .dimensions import DimensionVectorError, parse_dimension_vector, serialise_dimension_vector
from .registry import canonical_unit_for_vector
from .semantics import resolve_quantity_kind

_DIMENSIONED_VALUE_RE = re.compile(r"^\s*(\[[^\]]+\])\s+(.+?)\s*$", re.DOTALL)
_SCALAR_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


class OpenFOAMQuantityError(ValueError):
    """Raised when an OpenFOAM dimensioned value cannot be safely decoded."""


def _scalar_or_raw(raw: str) -> float | int | str:
    token = raw.strip()
    if not _SCALAR_RE.match(token):
        return token
    value = float(token)
    return int(value) if value.is_integer() and not any(char in token.lower() for char in (".", "e")) else value


def build_openfoam_quantity_evidence(
    name: str,
    raw_dimensions: str,
    *,
    raw_value: str | None = None,
    context: str = "field",
    source_path: str | None = None,
    line: int | None = None,
) -> tuple[QuantityEvidence, Any]:
    try:
        vector = parse_dimension_vector(raw_dimensions)
    except DimensionVectorError as exc:
        raise OpenFOAMQuantityError(str(exc)) from exc

    resolution = resolve_quantity_kind(name, vector, context=context)
    magnitude: float | int | None = None
    value: Any = serialise_dimension_vector(vector)
    if raw_value is not None:
        parsed_value = _scalar_or_raw(raw_value)
        value = parsed_value
        if isinstance(parsed_value, (int, float)):
            magnitude = parsed_value

    canonical_unit = canonical_unit_for_vector(vector)
    warnings: list[str] = [
        "The canonical SI unit is derived from the OpenFOAM dimension vector; the source did not spell out a unit symbol."
    ]
    if raw_value is not None and magnitude is None:
        warnings.append("The value was preserved as text because it was not a scalar numeric literal.")

    evidence = QuantityEvidence(
        value=value,
        raw_value=(f"{raw_dimensions} {raw_value}".strip() if raw_value is not None else raw_dimensions),
        source_path=source_path,
        source_location=SourceLocation(line_start=line, line_end=line) if line else None,
        parser="caereflex.units.openfoam",
        extraction_method="openfoam_dimension_vector",
        evidence_state=EvidenceState.exactly_parsed,
        confidence=1.0,
        warnings=warnings,
        magnitude=magnitude,
        unit=canonical_unit,
        dimension_vector=vector,
        quantity_kind=resolution.quantity_kind,
        normalized_magnitude=magnitude,
        normalized_unit=canonical_unit,
        unit_system="OpenFOAM dimension vector with canonical SI representation",
        metadata={
            "semantic_resolution": resolution.status,
            "expected_quantity_kinds": list(resolution.expected_kinds),
            "dimension_compatible_kinds": list(resolution.dimension_kinds),
            "context": context,
            "subject_name": name,
        },
    )
    check = check_dimensions(name, vector, context=context, source_path=source_path)
    return evidence, check


def parse_openfoam_dimensioned_value(
    name: str,
    raw: str,
    *,
    context: str = "material",
    source_path: str | None = None,
    line: int | None = None,
) -> tuple[QuantityEvidence, Any]:
    match = _DIMENSIONED_VALUE_RE.match(raw)
    if not match:
        raise OpenFOAMQuantityError("Expected '[M L T Θ N I J] value' syntax.")
    return build_openfoam_quantity_evidence(
        name,
        match.group(1),
        raw_value=match.group(2),
        context=context,
        source_path=source_path,
        line=line,
    )
