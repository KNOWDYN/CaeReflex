"""CLI for Gate 8 project, revision, run, comparison and review lifecycles."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from caereflex.lifecycle import (
    ASYNC_JOB_PROTOCOL_VERSION,
    HUMAN_REVIEW_PROTOCOL_VERSION,
    LIFECYCLE_PROTOCOL_VERSION,
    TEMPORAL_COMPARISON_PROTOCOL_VERSION,
    LifecycleStore,
    ReviewDecision,
    ReviewTargetType,
    compare_revisions,
)

lifecycle_app = typer.Typer(
    help="Manage projects, immutable revisions, runs, comparisons and human reviews.",
    no_args_is_help=True,
)
console = Console()


def _store(state_root: Path) -> LifecycleStore:
    return LifecycleStore(state_root)


def _print(value: Any, json_mode: bool = True) -> None:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    if json_mode:
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        console.print_json(json.dumps(payload, ensure_ascii=False, default=str))


@lifecycle_app.command("version")
def version() -> None:
    _print(
        {
            "lifecycle": LIFECYCLE_PROTOCOL_VERSION,
            "temporal_comparison": TEMPORAL_COMPARISON_PROTOCOL_VERSION,
            "human_review": HUMAN_REVIEW_PROTOCOL_VERSION,
            "async_job": ASYNC_JOB_PROTOCOL_VERSION,
        }
    )


@lifecycle_app.command("project-create")
def project_create(
    name: str,
    description: str = typer.Option(""),
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
) -> None:
    _print(_store(state_root).create_project(name, description=description))


@lifecycle_app.command("project-list")
def project_list(
    limit: int = typer.Option(100, min=1, max=1000),
    status: str | None = typer.Option(None),
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
    json_mode: bool = typer.Option(False, "--json"),
) -> None:
    rows = _store(state_root).list_projects(limit=limit, status=status)
    if json_mode:
        _print({"projects": [row.model_dump(mode="json") for row in rows]})
        return
    table = Table(title="CaeReflex projects")
    for heading in ("Project ID", "Name", "Status", "Updated"):
        table.add_column(heading)
    for row in rows:
        table.add_row(row.project_id, row.name, str(row.status), row.updated_at)
    console.print(table)


@lifecycle_app.command("project-show")
def project_show(
    project_id: str,
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
) -> None:
    _print(_store(state_root).get_project(project_id))


@lifecycle_app.command("project-archive")
def project_archive(
    project_id: str,
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
) -> None:
    _print(_store(state_root).archive_project(project_id))


@lifecycle_app.command("revision-create")
def revision_create(
    project_id: str,
    case_json: Path = typer.Option(..., "--case"),
    label: str | None = typer.Option(None),
    parent_revision_id: str | None = typer.Option(None, "--parent"),
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
) -> None:
    payload = json.loads(case_json.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise typer.BadParameter("case JSON must contain an object")
    _print(
        _store(state_root).create_revision(
            project_id,
            payload,
            label=label,
            parent_revision_id=parent_revision_id,
        )
    )


@lifecycle_app.command("revision-list")
def revision_list(
    project_id: str,
    limit: int = typer.Option(100, min=1, max=1000),
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
) -> None:
    _print(
        {
            "revisions": [
                row.model_dump(mode="json")
                for row in _store(state_root).list_revisions(project_id, limit)
            ]
        }
    )


@lifecycle_app.command("revision-show")
def revision_show(
    revision_id: str,
    include_case: bool = typer.Option(False, "--include-case"),
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
) -> None:
    store = _store(state_root)
    payload: dict[str, Any] = {
        "revision": store.get_revision(revision_id).model_dump(mode="json")
    }
    if include_case:
        payload["case"] = store.load_revision_payload(revision_id)
    _print(payload)


@lifecycle_app.command("run-list")
def run_list(
    project_id: str,
    limit: int = typer.Option(100, min=1, max=1000),
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
) -> None:
    _print(
        {
            "runs": [
                row.model_dump(mode="json")
                for row in _store(state_root).list_runs(project_id, limit)
            ]
        }
    )


@lifecycle_app.command("run-show")
def run_show(
    run_id: str,
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
) -> None:
    store = _store(state_root)
    _print(
        {
            "run": store.get_run(run_id).model_dump(mode="json"),
            "events": [
                item.model_dump(mode="json") for item in store.list_run_events(run_id)
            ],
        }
    )


@lifecycle_app.command("compare")
def compare(
    project_id: str,
    baseline_revision_id: str,
    candidate_revision_id: str,
    max_changes: int = typer.Option(200, min=1, max=500),
    ignore_path: list[str] = typer.Option([], "--ignore-path"),
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
) -> None:
    _print(
        compare_revisions(
            _store(state_root),
            project_id,
            baseline_revision_id,
            candidate_revision_id,
            ignore_paths=ignore_path,
            max_changes=max_changes,
        )
    )


@lifecycle_app.command("review-add")
def review_add(
    project_id: str,
    target_type: ReviewTargetType,
    target_id: str,
    reviewer_id: str,
    decision: ReviewDecision,
    statement: str,
    reviewer_display_name: str | None = typer.Option(None),
    supersedes_review_id: str | None = typer.Option(None, "--supersedes"),
    evidence_ref: list[str] = typer.Option([], "--evidence-ref"),
    signature: str | None = typer.Option(None),
    signature_scheme: str | None = typer.Option(None),
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
) -> None:
    _print(
        _store(state_root).add_review(
            project_id,
            target_type,
            target_id,
            reviewer_id=reviewer_id,
            reviewer_display_name=reviewer_display_name,
            decision=decision,
            statement=statement,
            evidence_refs=evidence_ref,
            supersedes_review_id=supersedes_review_id,
            signature=signature,
            signature_scheme=signature_scheme,
        )
    )


@lifecycle_app.command("review-list")
def review_list(
    project_id: str,
    target_type: ReviewTargetType | None = typer.Option(None),
    target_id: str | None = typer.Option(None),
    limit: int = typer.Option(100, min=1, max=1000),
    state_root: Path = typer.Option(Path(".caereflex"), "--state-root"),
) -> None:
    rows = _store(state_root).list_reviews(
        project_id,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
    )
    _print({"reviews": [row.model_dump(mode="json") for row in rows]})
