from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
try:
    from fastapi import FastAPI, Header, HTTPException, Query, status
    from fastapi.responses import JSONResponse, PlainTextResponse
    from pydantic import BaseModel, Field, field_validator
except Exception:  # pragma: no cover
    FastAPI = None

from caereflex.core.validation import assert_safe_workspace_path
from caereflex.exporters import agent_context_dict, case_to_dict
from caereflex.lifecycle import (
    ASYNC_JOB_PROTOCOL_VERSION,
    HUMAN_REVIEW_PROTOCOL_VERSION,
    LIFECYCLE_PROTOCOL_VERSION,
    TEMPORAL_COMPARISON_PROTOCOL_VERSION,
    AsyncJobService,
    InvalidTransitionError,
    JobQueueFullError,
    LifecycleStore,
    ReviewDecision,
    ReviewTargetType,
    compare_revisions,
)
from caereflex.services import (
    attach_crossref,
    export_case,
    inspect_path,
    list_case_store,
    load_case_from_store,
    save_case_to_store,
)
from caereflex.version import __version__


class BoundedRequestBodyMiddleware:
    """Buffer at most ``max_bytes`` and replay the body to the application."""

    def __init__(self, app: Any, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    response = JSONResponse(
                        status_code=413,
                        content={"detail": f"request body exceeds {self.max_bytes} bytes"},
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                response = JSONResponse(status_code=400, content={"detail": "invalid content-length header"})
                await response(scope, receive, send)
                return
        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            if message.get("type") != "http.request":
                continue
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.max_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={"detail": f"request body exceeds {self.max_bytes} bytes"},
                )
                await response(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        replayed = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal replayed
            if replayed:
                return {"type": "http.disconnect"}
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay_receive, send)


if FastAPI:
    class ImportRequest(BaseModel):
        path: str = Field(min_length=1, max_length=4096)
        adapter: str = Field(default="auto", min_length=1, max_length=100)
        attach_crossref: bool = False
        return_agent_context: bool = True
        options: dict[str, Any] = Field(default_factory=dict)

        @field_validator("options")
        @classmethod
        def bounded_options(cls, value: dict[str, Any]) -> dict[str, Any]:
            if len(value) > 32:
                raise ValueError("options may contain at most 32 keys")
            return value

    class CrossRefRequest(BaseModel):
        query: str | None = Field(default=None, max_length=2000)
        include_case_tags: bool = True
        limit: int = Field(default=10, ge=1, le=50)
        mailto: str | None = Field(default=None, max_length=320)
        mock_response: str | None = Field(default=None, max_length=4096)

    class ExportRequest(BaseModel):
        out: str | None = Field(default=None, max_length=4096)

    class ProjectCreateRequest(BaseModel):
        name: str = Field(min_length=1, max_length=200)
        description: str = Field(default="", max_length=4000)
        metadata: dict[str, Any] = Field(default_factory=dict)

        @field_validator("metadata")
        @classmethod
        def bounded_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
            if len(value) > 64:
                raise ValueError("metadata may contain at most 64 keys")
            if len(json.dumps(value, ensure_ascii=False, default=str)) > 32_768:
                raise ValueError("metadata exceeds 32768 serialized characters")
            return value

    class RevisionCreateRequest(BaseModel):
        case_id: str = Field(min_length=1, max_length=200)
        label: str | None = Field(default=None, max_length=200)
        parent_revision_id: str | None = Field(default=None, max_length=100)
        metadata: dict[str, Any] = Field(default_factory=dict)

        @field_validator("metadata")
        @classmethod
        def bounded_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
            if len(value) > 64:
                raise ValueError("metadata may contain at most 64 keys")
            return value

    class ComparisonRequest(BaseModel):
        project_id: str = Field(min_length=1, max_length=100)
        baseline_revision_id: str = Field(min_length=1, max_length=100)
        candidate_revision_id: str = Field(min_length=1, max_length=100)
        ignore_paths: list[str] = Field(default_factory=list, max_length=64)
        max_changes: int = Field(default=200, ge=1, le=500)

        @field_validator("ignore_paths")
        @classmethod
        def bounded_paths(cls, value: list[str]) -> list[str]:
            if any(not item.startswith("/") or len(item) > 512 for item in value):
                raise ValueError("ignore paths must be JSON-pointer patterns of at most 512 characters")
            return value

    class HumanReviewRequest(BaseModel):
        project_id: str = Field(min_length=1, max_length=100)
        target_type: ReviewTargetType
        target_id: str = Field(min_length=1, max_length=100)
        reviewer_id: str = Field(min_length=1, max_length=200)
        reviewer_display_name: str | None = Field(default=None, max_length=200)
        decision: ReviewDecision
        statement: str = Field(min_length=1, max_length=10_000)
        evidence_refs: list[str] = Field(default_factory=list, max_length=100)
        supersedes_review_id: str | None = Field(default=None, max_length=100)
        signature: str | None = Field(default=None, max_length=16_384)
        signature_scheme: str | None = Field(default=None, max_length=100)

    class AsyncInspectionRequest(BaseModel):
        project_id: str = Field(min_length=1, max_length=100)
        path: str = Field(min_length=1, max_length=4096)
        adapter: str = Field(default="auto", min_length=1, max_length=100)
        profile: str = Field(default="standard", pattern="^(catalog|standard|deep|forensic)$")
        attach_crossref: bool = False


def create_app(
    workspace: str | Path = ".",
    api_key: str | None = None,
    host: str = "127.0.0.1",
    *,
    max_workers: int = 2,
    max_queue: int = 32,
    max_request_body_bytes: int = 1024 * 1024,
):
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Install caereflex[server].")
    if max_request_body_bytes < 1024 or max_request_body_bytes > 10 * 1024 * 1024:
        raise ValueError("max_request_body_bytes must be between 1024 and 10485760")
    app = FastAPI(
        title="CaeReflex API",
        version=__version__,
        description="Bounded read-only CAE inspection and lifecycle services for agent workflows.",
    )
    app.add_middleware(BoundedRequestBodyMiddleware, max_bytes=max_request_body_bytes)
    ws = Path(workspace).expanduser().resolve()
    ws.mkdir(parents=True, exist_ok=True)
    external = host not in {"127.0.0.1", "localhost", "::1"}
    lifecycle = LifecycleStore(ws / ".caereflex")
    jobs = AsyncJobService(
        ws,
        lifecycle_store=lifecycle,
        max_workers=max_workers,
        max_queue=max_queue,
    )
    app.state.workspace = ws
    app.state.lifecycle_store = lifecycle
    app.state.job_service = jobs

    def check_key(x_api_key: str | None) -> None:
        if external and (not api_key or x_api_key != api_key):
            raise HTTPException(status_code=401, detail="API key required outside localhost.")

    def resolve_path(value: str) -> Path:
        candidate = Path(value).expanduser()
        path = candidate.resolve() if candidate.is_absolute() else (ws / candidate).resolve()
        return assert_safe_workspace_path(path, ws)

    def lifecycle_error(exc: Exception) -> HTTPException:
        message = str(exc)
        if "unknown " in message.lower() or message.lower().startswith("unknown"):
            return HTTPException(status_code=404, detail=message)
        if isinstance(exc, (InvalidTransitionError, JobQueueFullError)):
            return HTTPException(status_code=409, detail=message)
        return HTTPException(status_code=400, detail=message)

    @app.on_event("shutdown")
    def shutdown_jobs() -> None:
        jobs.shutdown(wait=False)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "success",
            "service": "caereflex",
            "version": __version__,
            "async_jobs": {"max_workers": max_workers, "max_queue": max_queue},
        }

    @app.get("/version")
    def version() -> dict[str, str]:
        return {"version": __version__}

    @app.get("/lifecycle/version")
    def lifecycle_version() -> dict[str, str]:
        return {
            "lifecycle": LIFECYCLE_PROTOCOL_VERSION,
            "temporal_comparison": TEMPORAL_COMPARISON_PROTOCOL_VERSION,
            "human_review": HUMAN_REVIEW_PROTOCOL_VERSION,
            "async_job": ASYNC_JOB_PROTOCOL_VERSION,
        }

    @app.get("/openapi.yaml", response_class=PlainTextResponse)
    def openapi_yaml() -> str:
        return yaml.safe_dump(app.openapi(), sort_keys=False)

    @app.post("/cases/import")
    def import_case(req: ImportRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            path = resolve_path(req.path)
            case = inspect_path(path, adapter=req.adapter, attach_crossref=req.attach_crossref)
            save_case_to_store(case, ws)
            data: dict[str, Any] = {
                "status": case.inspection.status,
                "case_id": case.case_id,
                "summary": case.agent_summary.summary,
                "warnings": [flag.message for flag in case.inspection_flags],
                "inspection_flags": [flag.model_dump(mode="json") for flag in case.inspection_flags],
                "provenance_summary": [item.event for item in case.provenance],
                "next_recommended_actions": ["create_revision", "get_agent_context", "export_case_report"],
            }
            if req.return_agent_context:
                data["data"] = {"agent_context": agent_context_dict(case)}
            return data
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/cases")
    def cases(
        limit: int = Query(default=100, ge=1, le=100),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        check_key(x_api_key)
        return {"status": "success", "cases": list_case_store(ws)[:limit]}

    @app.get("/cases/{case_id}")
    def get_case(case_id: str, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        return case_to_dict(load_case_from_store(case_id, ws))

    @app.get("/cases/{case_id}/summary")
    def get_summary(case_id: str, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        case = load_case_from_store(case_id, ws)
        return {
            "status": case.inspection.status,
            "case_id": case.case_id,
            "summary": case.agent_summary.summary,
            "detected_formats": case.detected_formats,
            "detected_tools": case.detected_tools,
        }

    @app.get("/cases/{case_id}/agent-context")
    def get_agent_context(case_id: str, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        return agent_context_dict(load_case_from_store(case_id, ws))

    @app.get("/cases/{case_id}/literature")
    def get_literature(case_id: str, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        case = load_case_from_store(case_id, ws)
        return {
            "literature_evidence": [item.model_dump(mode="json") for item in case.literature_evidence],
            "literature_context": case.literature_context.model_dump(mode="json"),
        }

    @app.get("/cases/{case_id}/inspection-flags")
    def get_flags(case_id: str, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        case = load_case_from_store(case_id, ws)
        return {"inspection_flags": [item.model_dump(mode="json") for item in case.inspection_flags]}

    @app.post("/cases/{case_id}/crossref/search")
    def crossref_search(case_id: str, req: CrossRefRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        from caereflex.services import search_crossref

        case = load_case_from_store(case_id, ws)
        records, context = search_crossref(
            case,
            query=req.query,
            include_case_tags=req.include_case_tags,
            limit=req.limit,
            mailto=req.mailto,
            mock_response=req.mock_response,
        )
        return {
            "records": [item.model_dump(mode="json") for item in records],
            "literature_context": context.model_dump(mode="json"),
        }

    @app.post("/cases/{case_id}/crossref/attach")
    def crossref_attach(case_id: str, req: CrossRefRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        case = attach_crossref(
            load_case_from_store(case_id, ws),
            query=req.query,
            include_case_tags=req.include_case_tags,
            limit=req.limit,
            mailto=req.mailto,
            mock_response=req.mock_response,
        )
        save_case_to_store(case, ws)
        return case_to_dict(case)

    @app.post("/cases/{case_id}/export/json")
    def export_json(case_id: str, req: ExportRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        return case_to_dict(load_case_from_store(case_id, ws))

    @app.post("/cases/{case_id}/export/markdown")
    def export_markdown(case_id: str, req: ExportRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        case = load_case_from_store(case_id, ws)
        out = resolve_path(req.out or f"{case_id}.md")
        export_case(case, "markdown", out)
        return {"status": "success", "out": out.relative_to(ws).as_posix()}

    @app.post("/cases/{case_id}/export/bibtex")
    def export_bibtex(case_id: str, req: ExportRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        case = load_case_from_store(case_id, ws)
        out = resolve_path(req.out or f"{case_id}.bib")
        export_case(case, "bibtex", out)
        return {"status": "success", "out": out.relative_to(ws).as_posix()}

    @app.post("/projects", status_code=status.HTTP_201_CREATED)
    def create_project(req: ProjectCreateRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return lifecycle.create_project(
                req.name,
                description=req.description,
                metadata=req.metadata,
            ).model_dump(mode="json")
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.get("/projects")
    def list_projects(
        limit: int = Query(default=50, ge=1, le=100),
        project_status: str | None = Query(default=None, alias="status"),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return {
                "projects": [
                    item.model_dump(mode="json")
                    for item in lifecycle.list_projects(limit, project_status)
                ]
            }
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.get("/projects/{project_id}")
    def get_project(project_id: str, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return lifecycle.get_project(project_id).model_dump(mode="json")
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.post("/projects/{project_id}/archive")
    def archive_project(project_id: str, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return lifecycle.archive_project(project_id).model_dump(mode="json")
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.post("/projects/{project_id}/revisions", status_code=status.HTTP_201_CREATED)
    def create_revision(
        project_id: str,
        req: RevisionCreateRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            case = load_case_from_store(req.case_id, ws)
            return lifecycle.create_revision(
                project_id,
                case_to_dict(case),
                label=req.label,
                parent_revision_id=req.parent_revision_id,
                metadata=req.metadata,
            ).model_dump(mode="json")
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.get("/projects/{project_id}/revisions")
    def list_revisions(
        project_id: str,
        limit: int = Query(default=50, ge=1, le=100),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return {
                "revisions": [
                    item.model_dump(mode="json")
                    for item in lifecycle.list_revisions(project_id, limit)
                ]
            }
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.get("/revisions/{revision_id}")
    def get_revision(
        revision_id: str,
        include_case: bool = Query(default=False),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            payload: dict[str, Any] = {
                "revision": lifecycle.get_revision(revision_id).model_dump(mode="json")
            }
            if include_case:
                payload["case"] = lifecycle.load_revision_payload(revision_id)
            return payload
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.get("/projects/{project_id}/runs")
    def list_runs(
        project_id: str,
        limit: int = Query(default=50, ge=1, le=100),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return {
                "runs": [
                    item.model_dump(mode="json")
                    for item in lifecycle.list_runs(project_id, limit)
                ]
            }
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.get("/runs/{run_id}")
    def get_run(run_id: str, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return {
                "run": lifecycle.get_run(run_id).model_dump(mode="json"),
                "events": [
                    item.model_dump(mode="json")
                    for item in lifecycle.list_run_events(run_id)
                ],
            }
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.post("/comparisons", status_code=status.HTTP_201_CREATED)
    def create_comparison(req: ComparisonRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return compare_revisions(
                lifecycle,
                req.project_id,
                req.baseline_revision_id,
                req.candidate_revision_id,
                ignore_paths=req.ignore_paths,
                max_changes=req.max_changes,
            ).model_dump(mode="json")
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.get("/comparisons/{comparison_id}")
    def get_comparison(comparison_id: str, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return lifecycle.get_comparison(comparison_id).model_dump(mode="json")
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.post("/reviews", status_code=status.HTTP_201_CREATED)
    def add_review(req: HumanReviewRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return lifecycle.add_review(
                req.project_id,
                req.target_type,
                req.target_id,
                reviewer_id=req.reviewer_id,
                reviewer_display_name=req.reviewer_display_name,
                decision=req.decision,
                statement=req.statement,
                evidence_refs=req.evidence_refs,
                supersedes_review_id=req.supersedes_review_id,
                signature=req.signature,
                signature_scheme=req.signature_scheme,
            ).model_dump(mode="json")
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.get("/reviews")
    def list_reviews(
        project_id: str,
        target_type: ReviewTargetType | None = Query(default=None),
        target_id: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return {
                "reviews": [
                    item.model_dump(mode="json")
                    for item in lifecycle.list_reviews(
                        project_id,
                        target_type=target_type,
                        target_id=target_id,
                        limit=limit,
                    )
                ]
            }
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.post("/jobs/inspect", status_code=status.HTTP_202_ACCEPTED)
    def submit_inspection(req: AsyncInspectionRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            path = resolve_path(req.path)
            record = jobs.submit_inspection(
                req.project_id,
                path,
                adapter=req.adapter,
                profile=req.profile,
                attach_crossref=req.attach_crossref,
            )
            return record.model_dump(mode="json")
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.post("/jobs/compare", status_code=status.HTTP_202_ACCEPTED)
    def submit_comparison(req: ComparisonRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return jobs.submit_comparison(
                req.project_id,
                req.baseline_revision_id,
                req.candidate_revision_id,
                ignore_paths=req.ignore_paths,
                max_changes=req.max_changes,
            ).model_dump(mode="json")
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.get("/jobs")
    def list_jobs(
        limit: int = Query(default=50, ge=1, le=100),
        job_status: str | None = Query(default=None, alias="status"),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return {
                "jobs": [
                    item.model_dump(mode="json")
                    for item in jobs.list(limit, job_status)
                ]
            }
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
        check_key(x_api_key)
        try:
            return jobs.get(job_id).model_dump(mode="json")
        except Exception as exc:
            raise lifecycle_error(exc) from exc

    return app


app = create_app()


def generate_openapi_files(out_dir: str | Path = "openapi") -> None:
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    (directory / "openapi.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
    (directory / "openapi.yaml").write_text(yaml.safe_dump(schema, sort_keys=False), encoding="utf-8")
