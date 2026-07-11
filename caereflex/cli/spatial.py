"""CLI for bounded Gate 6 spatial graph queries and acceptance checks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import typer
from rich.console import Console
from rich.table import Table

from caereflex.core.config import CaeReflexConfig
from caereflex.spatial import (
    GATE6_FREEZE_VERSION,
    SPATIAL_QUERY_VERSION,
    SpatialBoundsMode,
    SpatialCompatibilityError,
    SpatialQueryError,
    SpatialQueryLimits,
    SpatialQueryService,
    SpatialTraversalDirection,
    validate_spatial_store,
)

spatial_app = typer.Typer(
    help="Query persisted spatial graphs without materialising heavy arrays.",
    no_args_is_help=True,
)
console = Console()


def _root(state_root: Path | None) -> Path:
    return state_root or CaeReflexConfig().execution_state_dir


def _service(
    state_root: Path | None,
    *,
    max_results: int = 100,
    max_scan_rows: int = 10_000,
    max_depth: int = 8,
) -> SpatialQueryService:
    return SpatialQueryService(
        _root(state_root),
        limits=SpatialQueryLimits(
            max_results=max_results,
            max_scan_rows=max_scan_rows,
            max_depth=max_depth,
        ),
    )


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _vector(value: str, label: str) -> tuple[float, float, float]:
    try:
        items = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise typer.BadParameter(f"{label} must contain three comma-separated numbers") from exc
    if len(items) != 3:
        raise typer.BadParameter(f"{label} must contain exactly three comma-separated numbers")
    return items  # type: ignore[return-value]


def _payload(result: object) -> dict:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return dict(result)  # type: ignore[arg-type]


def _print(result: object, json_mode: bool) -> None:
    payload = _payload(result)
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return
    if payload.get("graph_id"):
        console.print(f"[bold]Graph:[/bold] {payload['graph_id']}")
    console.print(
        f"[bold]Operation:[/bold] {payload.get('operation', 'validate')} · "
        f"[bold]Returned:[/bold] {payload.get('returned_count', 0)} · "
        f"[bold]Truncated:[/bold] {payload.get('truncated', False)}"
    )
    rows: list[tuple[str, str, str]] = []
    for graph in payload.get("graphs", []):
        rows.append((str(graph.get("graph_id")), "graph", str(graph.get("name") or "")))
    for frame in payload.get("frames", []):
        rows.append((str(frame.get("frame_id")), "frame", str(frame.get("name") or "")))
    for entity in payload.get("entities", []):
        rows.append((str(entity.get("entity_id")), str(entity.get("entity_kind")), str(entity.get("name") or "")))
    for relation in payload.get("relations", []):
        rows.append((str(relation.get("relation_id")), str(relation.get("relation_kind")), f"{relation.get('source_entity_id')} → {relation.get('target_entity_id')}"))
    for link in payload.get("array_links", []):
        rows.append((str(link.get("link_id")), str(link.get("role")), str(link.get("array_id"))))
    if rows:
        table = Table()
        table.add_column("ID")
        table.add_column("Kind")
        table.add_column("Context")
        for row in rows:
            table.add_row(*row)
        console.print(table)
    elif "accepted" in payload:
        console.print(f"[bold]Accepted:[/bold] {payload['accepted']}")
        for issue in payload.get("errors", []):
            console.print(f"[red]{issue.get('code')}[/red] {issue.get('message')}")


def _fail(exc: Exception) -> None:
    console.print(f"[red]{exc}[/red]")
    raise typer.Exit(1)


@spatial_app.command("graphs")
def graphs(
    case_id: str | None = typer.Option(None, "--case-id"),
    limit: int = typer.Option(100, min=1, max=1000),
    offset: int = typer.Option(0, min=0),
    state_root: Path | None = typer.Option(None, "--state-root"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        _print(_service(state_root, max_results=limit).list_graphs(case_id=case_id, limit=limit, offset=offset), json_mode)
    except SpatialQueryError as exc:
        _fail(exc)


@spatial_app.command("show")
def show(
    graph_id: str,
    state_root: Path | None = typer.Option(None, "--state-root"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        _print(_service(state_root).describe_graph(graph_id), json_mode)
    except SpatialQueryError as exc:
        _fail(exc)


@spatial_app.command("frames")
def frames(
    graph_id: str,
    evidence_status: str | None = typer.Option(None, "--evidence-status"),
    review_status: str | None = typer.Option(None, "--review-status"),
    limit: int = typer.Option(100, min=1, max=1000),
    offset: int = typer.Option(0, min=0),
    state_root: Path | None = typer.Option(None, "--state-root"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        _print(
            _service(state_root, max_results=limit).query_frames(
                graph_id,
                evidence_status=evidence_status,
                review_status=review_status,
                limit=limit,
                offset=offset,
            ),
            json_mode,
        )
    except (SpatialQueryError, ValueError) as exc:
        _fail(exc)


@spatial_app.command("entities")
def entities(
    graph_id: str,
    kinds: str | None = typer.Option(None, "--kinds", help="Comma-separated entity kinds."),
    domains: str | None = typer.Option(None, "--domains", help="Comma-separated spatial domains."),
    frame_id: str | None = typer.Option(None, "--frame-id"),
    dimension: int | None = typer.Option(None, "--dimension", min=0, max=3),
    name_contains: str | None = typer.Option(None, "--name-contains"),
    source_path: str | None = typer.Option(None, "--source-path"),
    limit: int = typer.Option(100, min=1, max=1000),
    offset: int = typer.Option(0, min=0),
    max_scan_rows: int = typer.Option(10_000, "--max-scan-rows", min=1),
    state_root: Path | None = typer.Option(None, "--state-root"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        _print(
            _service(state_root, max_results=limit, max_scan_rows=max_scan_rows).query_entities(
                graph_id,
                entity_kinds=_csv(kinds),
                domains=_csv(domains),
                coordinate_frame_id=frame_id,
                topological_dimension=dimension,
                name_contains=name_contains,
                source_path=source_path,
                limit=limit,
                offset=offset,
            ),
            json_mode,
        )
    except (SpatialQueryError, ValueError) as exc:
        _fail(exc)


@spatial_app.command("relations")
def relations(
    graph_id: str,
    entity_id: str | None = typer.Option(None, "--entity-id"),
    kinds: str | None = typer.Option(None, "--kinds", help="Comma-separated relation kinds."),
    direction: SpatialTraversalDirection = typer.Option(SpatialTraversalDirection.both),
    limit: int = typer.Option(100, min=1, max=1000),
    offset: int = typer.Option(0, min=0),
    state_root: Path | None = typer.Option(None, "--state-root"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        _print(
            _service(state_root, max_results=limit).query_relations(
                graph_id,
                entity_id=entity_id,
                relation_kinds=_csv(kinds),
                direction=direction,
                limit=limit,
                offset=offset,
            ),
            json_mode,
        )
    except (SpatialQueryError, ValueError) as exc:
        _fail(exc)


@spatial_app.command("neighbours")
def neighbours(
    graph_id: str,
    seed_entity_id: str,
    kinds: str | None = typer.Option(None, "--kinds", help="Comma-separated relation kinds."),
    direction: SpatialTraversalDirection = typer.Option(SpatialTraversalDirection.both),
    depth: int = typer.Option(1, "--depth", min=1, max=8),
    include_seed: bool = typer.Option(False, "--include-seed"),
    limit: int = typer.Option(100, min=1, max=1000),
    state_root: Path | None = typer.Option(None, "--state-root"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        _print(
            _service(state_root, max_results=limit, max_depth=8).neighbours(
                graph_id,
                seed_entity_id,
                relation_kinds=_csv(kinds),
                direction=direction,
                max_depth=depth,
                include_seed=include_seed,
                limit=limit,
            ),
            json_mode,
        )
    except (SpatialQueryError, ValueError) as exc:
        _fail(exc)


@spatial_app.command("bounds")
def bounds(
    graph_id: str,
    frame_id: str = typer.Option(..., "--frame-id"),
    minimum: str = typer.Option(..., "--minimum", help="x,y,z"),
    maximum: str = typer.Option(..., "--maximum", help="x,y,z"),
    mode: SpatialBoundsMode = typer.Option(SpatialBoundsMode.intersects),
    active_dimensions: int = typer.Option(3, min=1, max=3),
    kinds: str | None = typer.Option(None, "--kinds"),
    limit: int = typer.Option(100, min=1, max=1000),
    offset: int = typer.Option(0, min=0),
    max_scan_rows: int = typer.Option(10_000, "--max-scan-rows", min=1),
    state_root: Path | None = typer.Option(None, "--state-root"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        _print(
            _service(state_root, max_results=limit, max_scan_rows=max_scan_rows).query_bounds(
                graph_id,
                coordinate_frame_id=frame_id,
                minimum=_vector(minimum, "minimum"),
                maximum=_vector(maximum, "maximum"),
                active_dimensions=active_dimensions,
                mode=mode,
                entity_kinds=_csv(kinds),
                limit=limit,
                offset=offset,
            ),
            json_mode,
        )
    except (SpatialQueryError, ValueError) as exc:
        _fail(exc)


@spatial_app.command("arrays")
def arrays(
    graph_id: str,
    owner_entity_id: str | None = typer.Option(None, "--owner-entity-id"),
    owner_frame_id: str | None = typer.Option(None, "--owner-frame-id"),
    roles: str | None = typer.Option(None, "--roles"),
    limit: int = typer.Option(100, min=1, max=1000),
    offset: int = typer.Option(0, min=0),
    state_root: Path | None = typer.Option(None, "--state-root"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        _print(
            _service(state_root, max_results=limit).query_array_links(
                graph_id,
                owner_entity_id=owner_entity_id,
                owner_frame_id=owner_frame_id,
                roles=_csv(roles),
                limit=limit,
                offset=offset,
            ),
            json_mode,
        )
    except (SpatialQueryError, ValueError) as exc:
        _fail(exc)


@spatial_app.command("validate")
def validate(
    graph_id: str,
    state_root: Path | None = typer.Option(None, "--state-root"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    try:
        report = validate_spatial_store(_root(state_root), graph_id)
        _print(report, json_mode)
        if not report.accepted:
            raise typer.Exit(1)
    except (SpatialCompatibilityError, SpatialQueryError) as exc:
        _fail(exc)


@spatial_app.command("version")
def version(json_mode: bool = typer.Option(False, "--json")) -> None:
    payload = {
        "query_version": SPATIAL_QUERY_VERSION,
        "freeze_version": GATE6_FREEZE_VERSION,
    }
    if json_mode:
        typer.echo(json.dumps(payload, indent=2))
    else:
        console.print(f"Spatial query: {SPATIAL_QUERY_VERSION}\nGate 6 freeze: {GATE6_FREEZE_VERSION}")


__all__ = ["spatial_app"]
