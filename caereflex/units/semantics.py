"""Conservative quantity semantics for common CAE fields and properties."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .dimensions import DimensionVector, parse_dimension_vector, vectors_equal


@dataclass(frozen=True)
class QuantityDefinition:
    name: str
    dimension_vector: DimensionVector
    description: str


def _v(*values: float) -> DimensionVector:
    return parse_dimension_vector(values)


QUANTITY_DEFINITIONS: dict[str, QuantityDefinition] = {
    "dimensionless": QuantityDefinition("dimensionless", _v(0, 0, 0, 0, 0, 0, 0), "Dimensionless quantity."),
    "length": QuantityDefinition("length", _v(0, 1, 0, 0, 0, 0, 0), "Length."),
    "area": QuantityDefinition("area", _v(0, 2, 0, 0, 0, 0, 0), "Area."),
    "volume": QuantityDefinition("volume", _v(0, 3, 0, 0, 0, 0, 0), "Volume."),
    "time": QuantityDefinition("time", _v(0, 0, 1, 0, 0, 0, 0), "Time."),
    "frequency": QuantityDefinition("frequency", _v(0, 0, -1, 0, 0, 0, 0), "Frequency or inverse time."),
    "mass": QuantityDefinition("mass", _v(1, 0, 0, 0, 0, 0, 0), "Mass."),
    "velocity": QuantityDefinition("velocity", _v(0, 1, -1, 0, 0, 0, 0), "Velocity."),
    "acceleration": QuantityDefinition("acceleration", _v(0, 1, -2, 0, 0, 0, 0), "Acceleration."),
    "density": QuantityDefinition("density", _v(1, -3, 0, 0, 0, 0, 0), "Mass density."),
    "force": QuantityDefinition("force", _v(1, 1, -2, 0, 0, 0, 0), "Force."),
    "pressure": QuantityDefinition("pressure", _v(1, -1, -2, 0, 0, 0, 0), "Thermodynamic or mechanical pressure."),
    "kinematic_pressure": QuantityDefinition("kinematic_pressure", _v(0, 2, -2, 0, 0, 0, 0), "Pressure divided by density, as used by incompressible OpenFOAM solvers."),
    "energy": QuantityDefinition("energy", _v(1, 2, -2, 0, 0, 0, 0), "Energy."),
    "specific_energy": QuantityDefinition("specific_energy", _v(0, 2, -2, 0, 0, 0, 0), "Energy per unit mass."),
    "power": QuantityDefinition("power", _v(1, 2, -3, 0, 0, 0, 0), "Power."),
    "dynamic_viscosity": QuantityDefinition("dynamic_viscosity", _v(1, -1, -1, 0, 0, 0, 0), "Dynamic viscosity."),
    "kinematic_viscosity": QuantityDefinition("kinematic_viscosity", _v(0, 2, -1, 0, 0, 0, 0), "Kinematic viscosity."),
    "eddy_kinematic_viscosity": QuantityDefinition("eddy_kinematic_viscosity", _v(0, 2, -1, 0, 0, 0, 0), "Turbulent kinematic viscosity."),
    "thermal_diffusivity": QuantityDefinition("thermal_diffusivity", _v(0, 2, -1, 0, 0, 0, 0), "Thermal diffusivity."),
    "temperature": QuantityDefinition("temperature", _v(0, 0, 0, 1, 0, 0, 0), "Absolute temperature."),
    "thermal_conductivity": QuantityDefinition("thermal_conductivity", _v(1, 1, -3, -1, 0, 0, 0), "Thermal conductivity."),
    "specific_heat": QuantityDefinition("specific_heat", _v(0, 2, -2, -1, 0, 0, 0), "Specific heat capacity."),
    "specific_enthalpy": QuantityDefinition("specific_enthalpy", _v(0, 2, -2, 0, 0, 0, 0), "Specific enthalpy."),
    "mass_flow_rate": QuantityDefinition("mass_flow_rate", _v(1, 0, -1, 0, 0, 0, 0), "Mass flow rate."),
    "volumetric_flow_rate": QuantityDefinition("volumetric_flow_rate", _v(0, 3, -1, 0, 0, 0, 0), "Volumetric flow rate."),
    "turbulence_kinetic_energy": QuantityDefinition("turbulence_kinetic_energy", _v(0, 2, -2, 0, 0, 0, 0), "Turbulence kinetic energy per unit mass."),
    "turbulence_dissipation_rate": QuantityDefinition("turbulence_dissipation_rate", _v(0, 2, -3, 0, 0, 0, 0), "Turbulence kinetic-energy dissipation rate."),
    "specific_dissipation_rate": QuantityDefinition("specific_dissipation_rate", _v(0, 0, -1, 0, 0, 0, 0), "Specific turbulence dissipation rate."),
}

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "u": ("velocity",),
    "p": ("pressure", "kinematic_pressure"),
    "t": ("temperature",),
    "rho": ("density",),
    "k": ("turbulence_kinetic_energy",),
    "epsilon": ("turbulence_dissipation_rate",),
    "omega": ("specific_dissipation_rate",),
    "nut": ("eddy_kinematic_viscosity",),
    "alphat": ("thermal_diffusivity",),
    "h": ("specific_enthalpy",),
    "e": ("specific_energy",),
}

MATERIAL_ALIASES: dict[str, tuple[str, ...]] = {
    "nu": ("kinematic_viscosity",),
    "mu": ("dynamic_viscosity",),
    "dynamicviscosity": ("dynamic_viscosity",),
    "rho": ("density",),
    "cp": ("specific_heat",),
    "kappa": ("thermal_conductivity",),
    "alpha": ("thermal_diffusivity",),
}


@dataclass(frozen=True)
class QuantityResolution:
    quantity_kind: str | None
    status: str
    expected_kinds: tuple[str, ...]
    dimension_kinds: tuple[str, ...]


def expected_quantity_kinds(name: str, context: str = "field") -> tuple[str, ...]:
    aliases = FIELD_ALIASES if context == "field" else MATERIAL_ALIASES if context == "material" else {}
    return aliases.get(name.strip().lower(), ())


def quantity_kinds_for_vector(vector: Iterable[float]) -> tuple[str, ...]:
    parsed = parse_dimension_vector(vector)
    return tuple(
        name
        for name, definition in QUANTITY_DEFINITIONS.items()
        if vectors_equal(definition.dimension_vector, parsed)
    )


def resolve_quantity_kind(name: str, vector: Iterable[float], context: str = "field") -> QuantityResolution:
    parsed = parse_dimension_vector(vector)
    expected = expected_quantity_kinds(name, context=context)
    dimensional = quantity_kinds_for_vector(parsed)
    matches = tuple(kind for kind in expected if kind in dimensional)

    if len(matches) == 1:
        return QuantityResolution(matches[0], "name_and_dimensions", expected, dimensional)
    if len(matches) > 1:
        return QuantityResolution(None, "ambiguous", expected, dimensional)
    if expected:
        return QuantityResolution(None, "conflicted", expected, dimensional)
    if len(dimensional) == 1:
        return QuantityResolution(dimensional[0], "dimensions_only", expected, dimensional)
    if dimensional:
        return QuantityResolution(None, "ambiguous", expected, dimensional)
    return QuantityResolution(None, "unresolved", expected, dimensional)


def expected_vector(quantity_kind: str) -> DimensionVector:
    try:
        return QUANTITY_DEFINITIONS[quantity_kind].dimension_vector
    except KeyError as exc:
        raise KeyError(f"Unknown CaeReflex quantity kind: {quantity_kind}") from exc
