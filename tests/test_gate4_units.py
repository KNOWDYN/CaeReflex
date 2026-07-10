import math

import pytest

from caereflex.units import (
    DimensionVectorError,
    UnitInterpretationError,
    check_dimensions,
    convert_value,
    parse_dimension_vector,
    parse_quantity_expression,
    resolve_quantity_kind,
    unit_dimension_vector,
)


def test_openfoam_dimension_vector_requires_seven_components():
    assert parse_dimension_vector("[0 2 -1 0 0 0 0]") == (0.0, 2.0, -1.0, 0.0, 0.0, 0.0, 0.0)
    with pytest.raises(DimensionVectorError):
        parse_dimension_vector("[0 2 -1]")


def test_pint_parsing_normalises_pressure_to_si():
    parsed = parse_quantity_expression("1 bar")
    assert math.isclose(parsed["normalized_magnitude"], 100000.0)
    assert parsed["dimension_vector"] == [1, -1, -2, 0, 0, 0, 0]
    assert "kg" in parsed["normalized_unit"]


def test_offset_temperature_expression_is_parsed_safely():
    parsed = parse_quantity_expression("25 degC")
    assert math.isclose(parsed["normalized_magnitude"], 298.15, abs_tol=1e-10)
    assert parsed["dimension_vector"] == [0, 0, 0, 1, 0, 0, 0]
    assert parsed["normalized_unit"] == "K"


def test_unit_conversion_and_dimension_vector():
    converted = convert_value(1.0, "bar", "Pa")
    assert math.isclose(converted["output_magnitude"], 100000.0)
    assert converted["dimension_vector"] == [1, -1, -2, 0, 0, 0, 0]
    assert unit_dimension_vector("m/s") == (0.0, 1.0, -1.0, 0.0, 0.0, 0.0, 0.0)


def test_unknown_or_incompatible_units_fail_explicitly():
    with pytest.raises(UnitInterpretationError):
        parse_quantity_expression("1 definitely_not_a_unit")
    with pytest.raises(UnitInterpretationError):
        convert_value(1.0, "m", "s")


def test_name_and_dimensions_resolve_velocity():
    resolution = resolve_quantity_kind("U", (0, 1, -1, 0, 0, 0, 0), context="field")
    assert resolution.quantity_kind == "velocity"
    assert resolution.status == "name_and_dimensions"


def test_pressure_and_kinematic_pressure_remain_distinct():
    thermodynamic = resolve_quantity_kind("p", (1, -1, -2, 0, 0, 0, 0), context="field")
    kinematic = resolve_quantity_kind("p", (0, 2, -2, 0, 0, 0, 0), context="field")
    assert thermodynamic.quantity_kind == "pressure"
    assert kinematic.quantity_kind == "kinematic_pressure"


def test_conflicting_dimensions_block_automated_interpretation():
    check = check_dimensions("U", (1, -1, -2, 0, 0, 0, 0), context="field", source_path="0/U")
    assert check.status == "conflicted"
    assert check.diagnostic_code == "CRX-UNITS-DIMENSION-MISMATCH-001"
    assert check.blocks_automated_interpretation is True
