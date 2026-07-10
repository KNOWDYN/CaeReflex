"""Public dimensions, units, and quantity-semantics API."""
from .checks import check_dimensions, diagnostic_from_check
from .dimensions import (
    BASE_DIMENSIONS,
    DimensionVector,
    DimensionVectorError,
    dimension_expression,
    format_dimension_vector,
    parse_dimension_vector,
    serialise_dimension_vector,
    vectors_equal,
)
from .openfoam import (
    OpenFOAMQuantityError,
    build_openfoam_quantity_evidence,
    parse_openfoam_dimensioned_value,
)
from .registry import (
    UnitInterpretationError,
    canonical_unit_for_vector,
    convert_value,
    get_unit_registry,
    parse_quantity_expression,
    unit_dimension_vector,
)
from .semantics import (
    QUANTITY_DEFINITIONS,
    expected_quantity_kinds,
    expected_vector,
    quantity_kinds_for_vector,
    resolve_quantity_kind,
)

__all__ = [
    "BASE_DIMENSIONS",
    "DimensionVector",
    "DimensionVectorError",
    "OpenFOAMQuantityError",
    "QUANTITY_DEFINITIONS",
    "UnitInterpretationError",
    "build_openfoam_quantity_evidence",
    "canonical_unit_for_vector",
    "check_dimensions",
    "convert_value",
    "diagnostic_from_check",
    "dimension_expression",
    "expected_quantity_kinds",
    "expected_vector",
    "format_dimension_vector",
    "get_unit_registry",
    "parse_dimension_vector",
    "parse_openfoam_dimensioned_value",
    "parse_quantity_expression",
    "quantity_kinds_for_vector",
    "resolve_quantity_kind",
    "serialise_dimension_vector",
    "unit_dimension_vector",
    "vectors_equal",
]
