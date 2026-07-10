"""Dimension-vector primitives shared by CAE adapters and unit backends.

CaeReflex uses the OpenFOAM/SI base-dimension order:
[M, L, T, temperature, amount of substance, electric current, luminous intensity].
"""
from __future__ import annotations

import math
import re
from typing import Iterable

DimensionVector = tuple[float, float, float, float, float, float, float]

BASE_DIMENSIONS: tuple[str, ...] = (
    "mass",
    "length",
    "time",
    "temperature",
    "substance",
    "current",
    "luminosity",
)

BASE_UNIT_SYMBOLS: tuple[str, ...] = ("kg", "m", "s", "K", "mol", "A", "cd")

_VECTOR_RE = re.compile(r"^\s*\[\s*([^\]]+)\s*\]\s*$")


class DimensionVectorError(ValueError):
    """Raised when a seven-component dimension vector cannot be decoded."""


def _number(token: str) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise DimensionVectorError(f"Invalid dimension exponent: {token!r}") from exc
    if not math.isfinite(value):
        raise DimensionVectorError("Dimension exponents must be finite numbers.")
    return value


def parse_dimension_vector(raw: str | Iterable[float]) -> DimensionVector:
    """Parse a seven-component CAE dimension vector.

    String input must contain brackets. Iterable input is useful for schema and test
    validation, but still must contain exactly seven finite numeric values.
    """

    if isinstance(raw, str):
        match = _VECTOR_RE.match(raw)
        if not match:
            raise DimensionVectorError("Dimension vector must use '[M L T Θ N I J]' syntax.")
        tokens = match.group(1).split()
        values = tuple(_number(token) for token in tokens)
    else:
        values = tuple(float(value) for value in raw)
        if not all(math.isfinite(value) for value in values):
            raise DimensionVectorError("Dimension exponents must be finite numbers.")

    if len(values) != 7:
        raise DimensionVectorError(f"Expected seven dimension exponents, received {len(values)}.")
    return values  # type: ignore[return-value]


def normalise_exponent(value: float) -> int | float:
    rounded = round(value)
    return int(rounded) if math.isclose(value, rounded, rel_tol=0.0, abs_tol=1e-12) else value


def serialise_dimension_vector(vector: Iterable[float]) -> list[int | float]:
    parsed = parse_dimension_vector(vector)
    return [normalise_exponent(value) for value in parsed]


def format_dimension_vector(vector: Iterable[float]) -> str:
    values = " ".join(str(value) for value in serialise_dimension_vector(vector))
    return f"[{values}]"


def dimension_expression(vector: Iterable[float]) -> str:
    """Return a Pint-parseable SI base-unit expression for a dimension vector."""

    parsed = parse_dimension_vector(vector)
    factors = [
        f"{symbol} ** ({normalise_exponent(power)})"
        for symbol, power in zip(BASE_UNIT_SYMBOLS, parsed)
        if not math.isclose(power, 0.0, rel_tol=0.0, abs_tol=1e-12)
    ]
    return " * ".join(factors) if factors else "dimensionless"


def vectors_equal(left: Iterable[float], right: Iterable[float], tolerance: float = 1e-12) -> bool:
    a = parse_dimension_vector(left)
    b = parse_dimension_vector(right)
    return all(math.isclose(x, y, rel_tol=0.0, abs_tol=tolerance) for x, y in zip(a, b))
