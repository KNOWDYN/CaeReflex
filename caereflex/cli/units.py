"""Dimensions and units CLI commands."""
from __future__ import annotations

import json

import typer
from rich.console import Console

from caereflex.units import (
    QUANTITY_DEFINITIONS,
    UnitInterpretationError,
    check_dimensions,
    convert_value,
    parse_quantity_expression,
    unit_dimension_vector,
)

units_app = typer.Typer(help="Parse, convert, and dimensionally check engineering quantities.", no_args_is_help=True)
console = Console()


def _emit(payload: dict, json_mode: bool) -> None:
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        for key, value in payload.items():
            console.print(f"[bold]{key.replace('_', ' ').title()}:[/bold] {value}")


@units_app.command("parse")
def parse_command(
    expression: str,
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Parse a magnitude and unit expression, then normalize it to SI base units."""

    try:
        payload = {"status": "success", **parse_quantity_expression(expression)}
    except UnitInterpretationError as exc:
        if json_mode:
            _emit({"status": "failed", "diagnostic_code": "CRX-UNITS-PARSE-001", "error": str(exc)}, True)
        else:
            console.print(f"[red]CRX-UNITS-PARSE-001: {exc}[/red]")
        raise typer.Exit(1)
    _emit(payload, json_mode)


@units_app.command("convert")
def convert_command(
    value: float,
    from_unit: str,
    to_unit: str,
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Convert a scalar value between dimensionally compatible units."""

    try:
        payload = {"status": "success", **convert_value(value, from_unit, to_unit)}
    except UnitInterpretationError as exc:
        if json_mode:
            _emit({"status": "failed", "diagnostic_code": "CRX-UNITS-PARSE-001", "error": str(exc)}, True)
        else:
            console.print(f"[red]Unit conversion failed: {exc}[/red]")
        raise typer.Exit(1)
    _emit(payload, json_mode)


@units_app.command("check")
def check_command(
    unit: str,
    quantity_kind: str,
    subject_name: str = typer.Option("user_quantity", "--name"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    """Check whether a unit has the dimensions registered for a quantity kind."""

    if quantity_kind not in QUANTITY_DEFINITIONS:
        raise typer.BadParameter(f"Unknown quantity kind: {quantity_kind}")
    try:
        observed = unit_dimension_vector(unit)
    except UnitInterpretationError as exc:
        if json_mode:
            _emit({"status": "failed", "diagnostic_code": "CRX-UNITS-PARSE-001", "error": str(exc)}, True)
        else:
            console.print(f"[red]CRX-UNITS-PARSE-001: {exc}[/red]")
        raise typer.Exit(1)

    expected = QUANTITY_DEFINITIONS[quantity_kind].dimension_vector
    compatible = tuple(observed) == tuple(expected)
    payload = {
        "status": "consistent" if compatible else "conflicted",
        "subject_name": subject_name,
        "quantity_kind": quantity_kind,
        "unit": unit,
        "observed_dimension_vector": list(observed),
        "expected_dimension_vector": list(expected),
        "diagnostic_code": None if compatible else "CRX-UNITS-DIMENSION-MISMATCH-001",
        "blocks_automated_interpretation": not compatible,
    }
    _emit(payload, json_mode)
    if not compatible:
        raise typer.Exit(6)
