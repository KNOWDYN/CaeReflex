"""CLI commands for the Gate 5A isolated execution runtime."""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from caereflex.contracts import CaseManifest, ExecutionPolicy, InspectionBudget, InspectionPlan, InspectionProfile
from caereflex.execution import InspectionExecutionError, execute_inspection_plan, list_execution_backends

execution_app = typer.Typer(help="Run and inspect bounded deep-inspection backends.", no_args_is_help=True)
console = Console()


@execution_app.command("backends")
def backends(json_mode: bool = typer.Option(False, "--json")) -> None:
    rows = list_execution_backends()
    if json_mode:
        typer.echo(json.dumps({"execution_backends": rows}, indent=2, ensure_ascii=False))
        return
    table = Table(title="CaeReflex execution backends")
    for heading in ("Backend", "Version", "Source"):
        table.add_column(heading)
    for row in rows:
        table.add_row(row["backend_id"], row["backend_version"], row["source"])
    console.print(table)


def _default_state_root(source_root: Path) -> Path:
    resolved = source_root.expanduser().resolve()
    normalized_source = resolved.parent if resolved.is_file() else resolved
    return normalized_source.parent / ".caereflex"


@execution_app.command("run")
def run_execution(
    manifest_json: Path,
    source_root: Path = typer.Option(..., "--source-root"),
    backend: str = typer.Option("core.manifest-audit", "--backend"),
    plugin_id: str = typer.Option("core", "--plugin-id"),
    state_root: Path | None = typer.Option(None, "--state-root"),
    profile: InspectionProfile = typer.Option(InspectionProfile.deep),
    max_wall_time: float = typer.Option(30.0, min=0.1),
    max_bytes_read: int = typer.Option(25 * 1024 * 1024, min=0),
    max_files: int = typer.Option(500, min=1),
    backend_options_json: str = typer.Option("{}", "--backend-options-json"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        manifest = CaseManifest.model_validate_json(manifest_json.read_text(encoding="utf-8"))
        backend_options = json.loads(backend_options_json)
        if not isinstance(backend_options, dict):
            raise ValueError("backend options must decode to a JSON object")
        selected_paths = [entry.path for entry in manifest.entries if not entry.is_dir][:max_files]
        plan = InspectionPlan(
            plugin_id=plugin_id,
            profile=profile,
            selected_paths=selected_paths,
            backend_candidates=[backend],
            budget=InspectionBudget(
                max_files=max_files,
                max_depth=3,
                max_bytes_read=max_bytes_read,
                max_wall_time_seconds=max_wall_time,
            ),
        )
        result = execute_inspection_plan(
            manifest,
            plan,
            backend_id=backend,
            source_root=source_root,
            state_root=state_root or _default_state_root(source_root),
            backend_options=backend_options,
            policy=ExecutionPolicy(),
        )
    except (OSError, ValueError, InspectionExecutionError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    payload = result.model_dump(mode="json")
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        console.print_json(json.dumps(payload, ensure_ascii=False, default=str))
    status = str(payload["status"])
    raise typer.Exit(0 if status == "success" else 2 if status == "partial_success" else 1)
