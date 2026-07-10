from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from caereflex.cli.arrays import arrays_app
from caereflex.cli.execution import execution_app
from caereflex.cli.jobs import jobs_app
from caereflex.cli.units import units_app
from caereflex.contracts import InspectionBudget, InspectionProfile
from caereflex.core.config import CaeReflexConfig
from caereflex.core.models import ReflexCase
from caereflex.diagnostics import DIAGNOSTICS, explain_diagnostic
from caereflex.discovery import CatalogStore
from caereflex.plugins import adapter_capabilities, get_adapter_plugin, probe_manifest
from caereflex.services import (
    attach_crossref, doctor_report, export_case, inspect_path, list_examples,
    load_case, run_example, save_case, scan_path, search_crossref,
)
from caereflex.version import __version__

app = typer.Typer(help="CaeReflex: agent-readable engineering evidence for simulation artefacts.", no_args_is_help=True)
console = Console()


def group(name: str, help_text: str) -> typer.Typer:
    item = typer.Typer(help=help_text)
    app.add_typer(item, name=name)
    return item


crossref_app = group("crossref", "CrossRef metadata commands.")
export_app = group("export", "Export commands.")
examples_app = group("examples", "Bundled examples.")
adapters_app = group("adapters", "Inspect adapter capabilities and probe manifests.")
schema_app = group("schema", "Inspect and validate schemas.")
diagnostics_app = group("diagnostics", "Explain stable diagnostic codes.")
cache_app = group("cache", "Manage the catalogue cache.")
app.add_typer(units_app, name="units")
app.add_typer(execution_app, name="execution")
app.add_typer(arrays_app, name="arrays")
app.add_typer(jobs_app, name="jobs")


def emit(data: dict[str, Any], json_mode: bool = False) -> None:
    if json_mode:
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return
    console.print(f"[bold]Status:[/bold] {data.get('status')}")
    for label, key in (("Case ID", "case_id"), ("Manifest ID", "manifest_id")):
        if data.get(key):
            console.print(f"[bold]{label}:[/bold] {data[key]}")
    if data.get("summary"):
        console.print(data["summary"])
    if data.get("outputs"):
        console.print("[bold]Outputs:[/bold]")
        for key, value in data["outputs"].items():
            console.print(f"- {key}: {value}")
    if data.get("warnings"):
        console.print("[bold yellow]Warnings:[/bold yellow]")
        for warning in data["warnings"]:
            console.print(f"- {warning}")


def exit_for(status: str) -> None:
    raise typer.Exit({"success": 0, "partial_success": 2, "unsupported": 3}.get(status, 1))


def status_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


@app.command("version")
def version() -> None:
    typer.echo(__version__)


@app.command("doctor")
def doctor(json_mode: bool = typer.Option(False, "--json")) -> None:
    report = doctor_report()
    if json_mode:
        emit(report, True)
        return
    console.print(f"CaeReflex {report['caereflex_version']} · contracts {report['contract_version']}")
    table = Table(title="Dependency availability")
    table.add_column("Dependency")
    table.add_column("Available")
    for name, available in report["dependencies"].items():
        table.add_row(name, "yes" if available else "no")
    console.print(table)


def budget(max_files: int, max_depth: int, max_bytes_read: int, max_wall_time: float) -> InspectionBudget:
    return InspectionBudget(max_files=max_files, max_depth=max_depth, max_bytes_read=max_bytes_read, max_wall_time_seconds=max_wall_time)


@app.command("scan")
def scan_cmd(
    path: str,
    out: Path | None = typer.Option(None),
    profile: InspectionProfile = typer.Option(InspectionProfile.catalog),
    max_files: int = typer.Option(500, min=1),
    max_depth: int = typer.Option(3, min=0),
    max_bytes_read: int = typer.Option(25 * 1024 * 1024, min=0),
    max_wall_time: float = typer.Option(30.0, min=0.1),
    cache: Path | None = typer.Option(None),
    no_cache: bool = typer.Option(False, "--no-cache"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    manifest, diff = scan_path(path, profile=profile, budget=budget(max_files, max_depth, max_bytes_read, max_wall_time), cache_path=cache, use_cache=not no_cache)
    payload = manifest.model_dump(mode="json") | {"catalog_diff": diff}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if json_mode:
        emit(payload, True)
        return
    warnings = [item.message for item in manifest.diagnostics if item.severity in {"warning", "error"}]
    emit({
        "status": "partial_success" if manifest.truncated else "success",
        "manifest_id": manifest.manifest_id,
        "summary": f"Catalogued {len(manifest.entries)} entries; detected {', '.join(manifest.case_hints) or 'no supported case family'}.",
        "outputs": {"manifest": str(out)} if out else {},
        "warnings": warnings,
    })


@app.command("inspect")
def inspect_cmd(
    path: Path,
    out: Path = typer.Option(Path("caereflex.json")),
    agent_context: Path | None = typer.Option(None),
    report: Path | None = typer.Option(None),
    adapter: str = typer.Option("auto"),
    profile: InspectionProfile = typer.Option(InspectionProfile.standard),
    manifest_out: Path | None = typer.Option(None),
    attach_crossref_flag: bool = typer.Option(False, "--attach-crossref"),
    crossref_limit: int = 10,
    json_mode: bool = typer.Option(False, "--json"),
    max_file_size_mb: int = 25,
    max_scan_depth: int = 3,
    max_scan_files: int = 500,
) -> None:
    config = CaeReflexConfig(max_file_size_mb=max_file_size_mb, max_scan_depth=max_scan_depth, max_scan_files=max_scan_files)
    manifest, _ = scan_path(path, profile=profile, budget=InspectionBudget(max_files=max_scan_files, max_depth=max_scan_depth, max_bytes_read=config.max_file_size_bytes))
    if manifest_out:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    case = inspect_path(path, adapter=adapter, config=config, attach_crossref=attach_crossref_flag, crossref_kwargs={"limit": crossref_limit}, profile=profile, manifest=manifest)
    save_case(case, out)
    outputs = {"caereflex_json": str(out)}
    if agent_context:
        export_case(case, "agent-context", agent_context)
        outputs["agent_context"] = str(agent_context)
    if report:
        export_case(case, "markdown", report)
        outputs["report"] = str(report)
    if manifest_out:
        outputs["manifest"] = str(manifest_out)
    data = {"status": status_value(case.inspection.status), "case_id": case.case_id, "summary": case.agent_summary.summary, "outputs": outputs, "warnings": [flag.message for flag in case.inspection_flags]}
    emit(data, json_mode)
    exit_for(data["status"])


def legacy_inspect(path: Path, adapter: str, out: Path, json_mode: bool) -> None:
    case = inspect_path(path, adapter=adapter)
    save_case(case, out)
    data = {"status": status_value(case.inspection.status), "case_id": case.case_id, "summary": case.agent_summary.summary, "outputs": {"caereflex_json": str(out)}, "warnings": [flag.message for flag in case.inspection_flags]}
    emit(data, json_mode)
    exit_for(data["status"])


@app.command("inspect-gmsh", deprecated=True)
def inspect_gmsh(path: Path, out: Path = typer.Option(Path("gmsh_case.json")), json_mode: bool = typer.Option(False, "--json")) -> None:
    legacy_inspect(path, "gmsh", out, json_mode)


@app.command("inspect-openfoam", deprecated=True)
def inspect_openfoam(path: Path, out: Path = typer.Option(Path("openfoam_case.json")), json_mode: bool = typer.Option(False, "--json")) -> None:
    legacy_inspect(path, "openfoam", out, json_mode)


@app.command("inspect-vtk", deprecated=True)
def inspect_vtk(path: Path, out: Path = typer.Option(Path("vtk_case.json")), json_mode: bool = typer.Option(False, "--json")) -> None:
    legacy_inspect(path, "vtk", out, json_mode)


@adapters_app.command("list")
def adapters_list(json_mode: bool = typer.Option(False, "--json")) -> None:
    items = [item.model_dump(mode="json") for item in adapter_capabilities()]
    if json_mode:
        emit({"adapters": items}, True)
        return
    table = Table(title="CaeReflex adapters")
    for heading in ("Plugin", "Formats", "Geometry", "Fields"):
        table.add_column(heading)
    for item in items:
        table.add_row(item["plugin_id"], ", ".join(item["formats"]), item["geometry_support"], item["field_support"])
    console.print(table)


@adapters_app.command("info")
def adapters_info(plugin_id: str, json_mode: bool = typer.Option(False, "--json")) -> None:
    plugin = get_adapter_plugin(plugin_id)
    if plugin is None:
        raise typer.BadParameter(f"Unknown adapter plugin: {plugin_id}")
    emit(plugin.capabilities().model_dump(mode="json"), True)


@adapters_app.command("probe")
def adapters_probe(path: str, json_mode: bool = typer.Option(False, "--json")) -> None:
    manifest, _ = scan_path(path)
    results = [item.model_dump(mode="json") for item in probe_manifest(manifest)]
    if json_mode:
        emit({"manifest_id": manifest.manifest_id, "probes": results}, True)
        return
    table = Table(title=f"Adapter probe · {manifest.manifest_id}")
    for heading in ("Plugin", "Supported", "Score", "Reasons"):
        table.add_column(heading)
    for item in results:
        table.add_row(item["plugin_id"], str(item["supported"]), f"{item['score']:.2f}", ", ".join(item["reasons"]))
    console.print(table)


@schema_app.command("show")
def schema_show() -> None:
    typer.echo(json.dumps(ReflexCase.model_json_schema(), indent=2, ensure_ascii=False))


@schema_app.command("validate")
def schema_validate(case_json: Path, json_mode: bool = typer.Option(False, "--json")) -> None:
    case = load_case(case_json)
    emit({"status": "success", "case_id": case.case_id, "schema_version": case.schema_version, "contract_version": case.contract_version}, json_mode)


@diagnostics_app.command("list")
def diagnostics_list(json_mode: bool = typer.Option(False, "--json")) -> None:
    if json_mode:
        emit({"diagnostics": DIAGNOSTICS}, True)
        return
    for code, item in DIAGNOSTICS.items():
        console.print(f"[bold]{code}[/bold] — {item['title']}")


@diagnostics_app.command("explain")
def diagnostics_explain(code: str, json_mode: bool = typer.Option(False, "--json")) -> None:
    item = explain_diagnostic(code)
    if item is None:
        raise typer.BadParameter(f"Unknown diagnostic code: {code}")
    data = {"code": code.upper(), **item}
    emit(data, True) if json_mode else console.print(f"[bold]{data['title']}[/bold]\n{data['explanation']}\nAction: {data['action']}")


@cache_app.command("clean")
def cache_clean(cache: Path = typer.Option(Path(".caereflex/catalog.sqlite3")), json_mode: bool = typer.Option(False, "--json")) -> None:
    emit({"status": "success", "removed_manifests": CatalogStore(cache).clear(), "cache": str(cache)}, json_mode)


@crossref_app.command("search")
def crossref_search(case_json: Path, query: str | None = None, include_case_tags: bool = True, limit: int = 10, mailto: str | None = None, mock_response: Path | None = typer.Option(None), out: Path | None = None, json_mode: bool = typer.Option(False, "--json")) -> None:
    case = load_case(case_json)
    records, context = search_crossref(case, query=query, include_case_tags=include_case_tags, limit=limit, mailto=mailto, mock_response=mock_response)
    data = {"status": "success", "queries": context.queries, "records": [record.model_dump(mode="json") for record in records], "literature_context": context.model_dump(mode="json")}
    if out:
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    emit({"status": "success", "summary": f"CrossRef search returned {len(records)} record(s).", "outputs": {"json": str(out)} if out else {}}, json_mode)


@crossref_app.command("attach")
def crossref_attach(case_json: Path, query: str | None = None, include_case_tags: bool = True, limit: int = 10, mailto: str | None = None, mock_response: Path | None = typer.Option(None), out: Path = typer.Option(Path("caereflex.with_literature.json")), json_mode: bool = typer.Option(False, "--json")) -> None:
    case = attach_crossref(case_json, query=query, include_case_tags=include_case_tags, limit=limit, mailto=mailto, mock_response=mock_response)
    save_case(case, out)
    emit({"status": "success", "case_id": case.case_id, "summary": case.literature_context.summary, "outputs": {"caereflex_json": str(out)}, "warnings": [flag.message for flag in case.inspection_flags]}, json_mode)


def export_command(case_json: Path, export_type: str, out: Path, key: str, json_mode: bool) -> None:
    export_case(case_json, export_type, out)
    emit({"status": "success", "outputs": {key: str(out)}}, json_mode)


@export_app.command("agent-context")
def export_agent_context(case_json: Path, out: Path = typer.Option(Path("agent_context.json")), json_mode: bool = typer.Option(False, "--json")) -> None:
    export_command(case_json, "agent-context", out, "agent_context", json_mode)


@export_app.command("markdown")
def export_markdown(case_json: Path, out: Path = typer.Option(Path("case_report.md")), json_mode: bool = typer.Option(False, "--json")) -> None:
    export_command(case_json, "markdown", out, "report", json_mode)


@export_app.command("bibtex")
def export_bibtex(case_json: Path, out: Path = typer.Option(Path("references.bib")), json_mode: bool = typer.Option(False, "--json")) -> None:
    export_command(case_json, "bibtex", out, "bibtex", json_mode)


@examples_app.command("list")
def examples_list(json_mode: bool = typer.Option(False, "--json")) -> None:
    names = list_examples()
    if json_mode:
        typer.echo(json.dumps({"examples": names}, indent=2))
    else:
        for name in names:
            typer.echo(name)


@examples_app.command("run")
def examples_run(name: str, out_dir: Path = Path("build"), json_mode: bool = typer.Option(False, "--json")) -> None:
    emit(run_example(name, out_dir=out_dir), json_mode)


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8765, workspace: Path = Path("."), api_key: str | None = None) -> None:
    if host not in {"127.0.0.1", "localhost"} and not api_key:
        console.print("[red]API key is mandatory outside localhost.[/red]")
        raise typer.Exit(5)
    try:
        import uvicorn
        from caereflex.server.app import create_app
    except Exception as exc:
        console.print(f"[red]Install [server] extras to run the REST server: {exc}[/red]")
        raise typer.Exit(4)
    uvicorn.run(create_app(workspace=workspace, api_key=api_key, host=host), host=host, port=port)


if __name__ == "__main__":
    app()
