"""CLI commands for persistent local execution-job records."""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from caereflex.jobs import JobStore, JobStoreError

jobs_app = typer.Typer(help="Inspect local execution-job records.", no_args_is_help=True)
console = Console()


@jobs_app.command("list")
def list_jobs(
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
    limit: int = typer.Option(100, min=1, max=1000),
    status: str | None = typer.Option(None),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    rows = [item.model_dump(mode="json") for item in JobStore(state_root).list(limit, status=status)]
    if json_mode:
        typer.echo(json.dumps({"jobs": rows}, indent=2, ensure_ascii=False, default=str))
        return
    table = Table(title="CaeReflex jobs")
    for heading in ("Job ID", "Kind", "Status", "Created", "Completed"):
        table.add_column(heading)
    for item in rows:
        table.add_row(
            item["job_id"],
            item["kind"],
            str(item["status"]),
            item["created_at"],
            str(item.get("completed_at") or ""),
        )
    console.print(table)


@jobs_app.command("show")
def show_job(
    job_id: str,
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        payload = JobStore(state_root).get(job_id).model_dump(mode="json")
    except JobStoreError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        console.print_json(json.dumps(payload, ensure_ascii=False, default=str))
