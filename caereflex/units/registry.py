"""Pint-backed parsing and conversion without leaking Pint objects into schemas."""
from __future__ import annotations

from functools import lru_cache
import re
from typing import Any

from pint import UnitRegistry
from pint.errors import DimensionalityError, OffsetUnitCalculusError, PintError, UndefinedUnitError

from .dimensions import DimensionVector, dimension_expression, parse_dimension_vector, serialise_dimension_vector

_DIMENSION_KEYS: dict[str, int] = {
    "[mass]": 0,
    "[length]": 1,
    "[time]": 2,
    "[temperature]": 3,
    "[substance]": 4,
    "[amount]": 4,
    "[current]": 5,
    "[luminosity]": 6,
    "[luminous_intensity]": 6,
}

_SCALAR_UNIT_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s+(.+?)\s*$"
)


class UnitInterpretationError(ValueError):
    """Raised when a unit expression cannot be safely interpreted."""


@lru_cache(maxsize=1)
def get_unit_registry() -> UnitRegistry:
    """Return the process-wide immutable-by-convention registry.

    Adapter code must not add definitions to this shared registry. Future custom unit
    registries must be created explicitly and identified in serialized evidence.
    """

    return UnitRegistry(autoconvert_offset_to_baseunit=False)


def _json_magnitude(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def dimensionality_to_vector(dimensionality: Any) -> DimensionVector:
    values = [0.0] * 7
    for key, power in dimensionality.items():
        key_text = str(key)
        index = _DIMENSION_KEYS.get(key_text)
        if index is None:
            raise UnitInterpretationError(f"Unsupported base dimension reported by Pint: {key_text}")
        values[index] = float(power)
    return parse_dimension_vector(values)


def canonical_unit_for_vector(vector: DimensionVector | list[float] | tuple[float, ...]) -> str:
    registry = get_unit_registry()
    expression = dimension_expression(vector)
    quantity = registry.Quantity(1, registry.parse_units(expression)).to_base_units()
    return f"{quantity.units:~}"


def _parse_quantity(registry: UnitRegistry, expression: str):
    """Parse an expression while treating a leading scalar and offset unit separately."""

    match = _SCALAR_UNIT_RE.match(expression)
    if match:
        magnitude = float(match.group(1))
        unit = registry.parse_units(match.group(2))
        return registry.Quantity(magnitude, unit)
    return registry.Quantity(expression)


def parse_quantity_expression(expression: str) -> dict[str, Any]:
    registry = get_unit_registry()
    try:
        quantity = _parse_quantity(registry, expression)
        normalized = quantity.to_base_units()
        vector = dimensionality_to_vector(quantity.dimensionality)
    except (PintError, ValueError, TypeError) as exc:
        raise UnitInterpretationError(str(exc)) from exc

    return {
        "expression": expression,
        "magnitude": _json_magnitude(quantity.magnitude),
        "unit": f"{quantity.units:~}",
        "normalized_magnitude": _json_magnitude(normalized.magnitude),
        "normalized_unit": f"{normalized.units:~}",
        "dimension_vector": serialise_dimension_vector(vector),
        "dimensionality": str(quantity.dimensionality),
        "unit_system": "Pint default registry / SI normalization",
    }


def convert_value(value: float, from_unit: str, to_unit: str) -> dict[str, Any]:
    registry = get_unit_registry()
    try:
        quantity = registry.Quantity(value, registry.parse_units(from_unit))
        converted = quantity.to(to_unit)
        vector = dimensionality_to_vector(quantity.dimensionality)
    except (UndefinedUnitError, DimensionalityError, OffsetUnitCalculusError, PintError, ValueError) as exc:
        raise UnitInterpretationError(str(exc)) from exc

    return {
        "input_magnitude": _json_magnitude(quantity.magnitude),
        "input_unit": f"{quantity.units:~}",
        "output_magnitude": _json_magnitude(converted.magnitude),
        "output_unit": f"{converted.units:~}",
        "dimension_vector": serialise_dimension_vector(vector),
    }


def unit_dimension_vector(unit: str) -> DimensionVector:
    registry = get_unit_registry()
    try:
        parsed = registry.parse_units(unit)
    except (PintError, ValueError) as exc:
        raise UnitInterpretationError(str(exc)) from exc
    return dimensionality_to_vector(parsed.dimensionality)
