"""CLI commands for deterministic physics-consistency rule packs."""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from caereflex.core.config import CaeReflexConfig
from caereflex.rules import (
    RULE_PROTOCOL_VERSION,
    RuleEvaluationError,
    evaluate_case_rules,
    get_rule_pack,
    list_rule_packs,
)
from caereflex.services import load_case, save_case

rules_app = typer.Typer(help="Evaluate versioned deterministic physics-consistency rules.", no_args_is_help=True)
console = Console()


def _emit(payload: dict, json_mode: bool) -> None:
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        console.print_json(json.dumps(payload, ensure_ascii=False, default=str))


def _status_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


@rules_app.command("version")
def version(json_mode: bool = typer.Option(False, "--json")) -> None:
    _emit({"protocol_version": RULE_PROTOCOL_VERSION}, json_mode)


@rules_app.command("packs")
def packs(json_mode: bool = typer.Option(False, "--json")) -> None:
    manifests = [item.model_dump(mode="json") for item in list_rule_packs()]
    if json_mode:
        _emit({"protocol_version": RULE_PROTOCOL_VERSION, "packs": manifests}, True)
        return
    table = Table(title="CaeReflex physics rule packs")
    for heading in ("Pack", "Version", "Domain", "Rules"):
        table.add_column(heading)
    for item in manifests:
        table.add_row(item["pack_id"], item["pack_version"], item["domain"], str(len(item["rule_ids"])))
    console.print(table)


@rules_app.command("describe")
def describe(pack_id: str, json_mode: bool = typer.Option(False, "--json")) -> None:
    try:
        pack = get_rule_pack(pack_id)
    except RuleEvaluationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    payload = pack.manifest.model_dump(mode="json")
    payload["rules"] = [rule.definition.model_dump(mode="json") for rule in pack.rules]
    _emit(payload, json_mode)


@rules_app.command("evaluate")
def evaluate(
    case_json: Path,
    pack_id: str = typer.Option("openfoam.cfd-core", "--pack"),
    state_root: Path | None = typer.Option(None, "--state-root"),
    out: Path | None = typer.Option(None, "--out"),
    attach: bool = typer.Option(True, "--attach/--no-attach"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        case = load_case(case_json)
        report = evaluate_case_rules(
            case,
            pack_id=pack_id,
            state_root=state_root or CaeReflexConfig().execution_state_dir,
            attach=attach,
        )
    except (RuleEvaluationError, ValueError, OSError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    if attach:
        save_case(case, out or case_json)
    elif out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    _emit(report.model_dump(mode="json"), json_mode)
    status = _status_value(report.status)
    if status == "inconsistent":
        raise typer.Exit(2)
    if status == "blocked":
        raise typer.Exit(3)


__all__ = ["rules_app"]
