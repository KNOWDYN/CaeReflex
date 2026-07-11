"""CLI for deterministic physics-consistency evaluation."""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from caereflex.physics import (
    OPENFOAM_CFD_RULE_PACK_VERSION,
    PHYSICS_RULE_PROTOCOL_VERSION,
    evaluate_openfoam_cfd,
    openfoam_rule_context,
)
from caereflex.services import load_case

physics_app = typer.Typer(help="Evaluate versioned deterministic physics-consistency rules.", no_args_is_help=True)
console = Console()


def _read_json(path: Path | None):
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@physics_app.command("version")
def version(json_mode: bool = typer.Option(False, "--json")) -> None:
    payload = {"protocol_version": PHYSICS_RULE_PROTOCOL_VERSION, "openfoam_cfd_pack_version": OPENFOAM_CFD_RULE_PACK_VERSION}
    typer.echo(json.dumps(payload, indent=2)) if json_mode else console.print_json(json.dumps(payload))


@physics_app.command("evaluate-openfoam")
def evaluate_openfoam(
    context_json: Path | None = typer.Option(None, "--context"),
    case_json: Path | None = typer.Option(None, "--case"),
    execution_json: Path | None = typer.Option(None, "--execution"),
    out: Path | None = typer.Option(None, "--out"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    if context_json is not None:
        context = _read_json(context_json)
        case_id = None
    else:
        case = load_case(case_json) if case_json is not None else None
        execution = _read_json(execution_json)
        context = openfoam_rule_context(case, execution)
        case_id = str(case.case_id) if case is not None else None
    if not isinstance(context, dict):
        raise typer.BadParameter("Rule context must be a JSON object")
    report = evaluate_openfoam_cfd(context, case_id=case_id)
    payload = report.model_dump(mode="json")
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    table = Table(title=f"OpenFOAM CFD rules · {report.pack.version}")
    table.add_column("Rule")
    table.add_column("Status")
    table.add_column("Message")
    for result in report.results:
        table.add_row(result.rule_id, str(result.status), result.message)
    console.print(table)
    console.print("Evidence-consistency checks only; no convergence, validation, certification or safety claim.")
