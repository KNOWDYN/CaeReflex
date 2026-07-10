"""CLI commands for lazy ArrayRef metadata and bounded queries."""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from caereflex.arrays import ArrayQueryError, ArrayService
from caereflex.core.config import CaeReflexConfig

arrays_app = typer.Typer(help="Describe and query registered lazy arrays.", no_args_is_help=True)
console = Console()


def _service(state_root: Path | None, max_elements: int = 10_000) -> ArrayService:
    root = state_root or CaeReflexConfig().execution_state_dir
    return ArrayService(root, max_elements_returned=max_elements)


def _print(payload: dict, json_mode: bool) -> None:
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        console.print_json(json.dumps(payload, ensure_ascii=False, default=str))


@arrays_app.command("list")
def list_arrays(
    state_root: Path | None = typer.Option(None, "--state-root"),
    limit: int = typer.Option(100, min=1, max=1000),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    rows = [item.model_dump(mode="json") for item in _service(state_root).list(limit)]
    if json_mode:
        _print({"arrays": rows}, True)
        return
    table = Table(title="Registered CaeReflex arrays")
    for heading in ("Array ID", "Shape", "Dtype", "Association", "Backend"):
        table.add_column(heading)
    for item in rows:
        table.add_row(
            str(item.get("array_id")),
            str(tuple(item.get("shape", []))),
            str(item.get("dtype")),
            str(item.get("association") or ""),
            str(item.get("backend") or ""),
        )
    console.print(table)


@arrays_app.command("describe")
def describe_array(
    array_id: str,
    state_root: Path | None = typer.Option(None, "--state-root"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        _print(_service(state_root).describe(array_id), json_mode)
    except ArrayQueryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)


@arrays_app.command("sample")
def sample_array(
    array_id: str,
    count: int = typer.Option(100, min=1),
    state_root: Path | None = typer.Option(None, "--state-root"),
    max_elements: int = typer.Option(10_000, min=1),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        _print(_service(state_root, max_elements).sample(array_id, count), json_mode)
    except ArrayQueryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)


@arrays_app.command("slice")
def slice_array(
    array_id: str,
    start: int = typer.Option(...),
    stop: int = typer.Option(...),
    step: int = typer.Option(1, min=1),
    state_root: Path | None = typer.Option(None, "--state-root"),
    max_elements: int = typer.Option(10_000, min=1),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        _print(_service(state_root, max_elements).slice(array_id, start, stop, step), json_mode)
    except ArrayQueryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)


@arrays_app.command("reduce")
def reduce_array(
    array_id: str,
    operation: str = typer.Option(..., help="min, max, mean, sum, or count"),
    component: int | None = typer.Option(None, min=0),
    state_root: Path | None = typer.Option(None, "--state-root"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        _print(_service(state_root).reduce(array_id, operation, component=component), json_mode)
    except ArrayQueryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
