"""Bounded in-process asynchronous lifecycle jobs."""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from caereflex.contracts import ExecutionStatus, JobRecord
from caereflex.core.config import CaeReflexConfig
from caereflex.core.provenance import utc_now_iso
from caereflex.jobs import JobStore
from caereflex.lifecycle.store import InvalidTransitionError, LifecycleStore
from caereflex.lifecycle.temporal import compare_revisions


class JobQueueFullError(RuntimeError):
    pass


class AsyncJobService:
    """A local bounded executor; not a distributed or restart-resumable queue."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        lifecycle_store: LifecycleStore | None = None,
        max_workers: int = 2,
        max_queue: int = 32,
    ) -> None:
        if max_workers < 1 or max_workers > 8:
            raise ValueError("max_workers must be between 1 and 8")
        if max_queue < 0 or max_queue > 128:
            raise ValueError("max_queue must be between 0 and 128")
        self.workspace = Path(workspace).expanduser().resolve()
        self.state_root = self.workspace / ".caereflex"
        self.lifecycle_store = lifecycle_store or LifecycleStore(self.state_root)
        self.job_store = JobStore(self.state_root)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="caereflex-job")
        self._slots = threading.BoundedSemaphore(max_workers + max_queue)
        self._closed = False
        self._recover_interrupted_jobs()

    def _recover_interrupted_jobs(self) -> None:
        for record in self.job_store.list(1000):
            if record.kind.startswith("lifecycle.") and str(record.status) in {
                ExecutionStatus.pending.value,
                ExecutionStatus.running.value,
            }:
                record.status = ExecutionStatus.failed
                record.completed_at = utc_now_iso()
                record.result_summary = {
                    **record.result_summary,
                    "error": "job was interrupted by a previous service shutdown and is not resumable",
                }
                self.job_store.put(record)
                run_id = record.request_summary.get("run_id")
                if run_id:
                    try:
                        run = self.lifecycle_store.get_run(str(run_id))
                        if str(run.status) not in {"success", "partial_success", "failed", "cancelled"}:
                            self.lifecycle_store.transition_run(
                                str(run_id),
                                "failed",
                                error="asynchronous job interrupted by service shutdown",
                            )
                    except Exception:
                        pass

    def _submit(
        self,
        *,
        kind: str,
        project_id: str,
        run_kind: str,
        request_summary: dict[str, Any],
        work: Callable[[], tuple[str, dict[str, Any], str | None]],
        input_revision_id: str | None = None,
    ) -> JobRecord:
        if self._closed:
            raise RuntimeError("job service is closed")
        if not self._slots.acquire(blocking=False):
            raise JobQueueFullError("asynchronous job capacity is full")
        job_id = f"job_{uuid.uuid4().hex[:16]}"
        try:
            run = self.lifecycle_store.create_run(
                project_id,
                run_kind,
                input_revision_id=input_revision_id,
                job_id=job_id,
                request_summary=request_summary,
            )
            record = JobRecord(
                job_id=job_id,
                kind=kind,
                status=ExecutionStatus.pending,
                request_summary={**request_summary, "project_id": project_id, "run_id": run.run_id},
            )
            self.job_store.put(record)
            self._executor.submit(self._execute, record.job_id, run.run_id, work)
            return record
        except Exception:
            self._slots.release()
            raise

    def _execute(
        self,
        job_id: str,
        run_id: str,
        work: Callable[[], tuple[str, dict[str, Any], str | None]],
    ) -> None:
        try:
            job = self.job_store.get(job_id)
            job.status = ExecutionStatus.running
            job.started_at = utc_now_iso()
            self.job_store.put(job)
            self.lifecycle_store.transition_run(run_id, "running")
            outcome, summary, result_revision_id = work()
            status_map = {
                "success": ExecutionStatus.success,
                "partial_success": ExecutionStatus.partial_success,
                "failed": ExecutionStatus.failed,
            }
            job.status = status_map.get(outcome, ExecutionStatus.failed)
            job.completed_at = utc_now_iso()
            job.result_summary = summary
            self.job_store.put(job)
            self.lifecycle_store.transition_run(
                run_id,
                outcome if outcome in {"success", "partial_success", "failed"} else "failed",
                result_revision_id=result_revision_id,
                result_summary=summary,
                error=summary.get("error") if outcome == "failed" else None,
            )
        except Exception as exc:
            try:
                job = self.job_store.get(job_id)
                job.status = ExecutionStatus.failed
                job.completed_at = utc_now_iso()
                job.result_summary = {"error": f"{type(exc).__name__}: {exc}"}
                self.job_store.put(job)
            finally:
                try:
                    self.lifecycle_store.transition_run(
                        run_id,
                        "failed",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                except InvalidTransitionError:
                    pass
        finally:
            self._slots.release()

    def submit_inspection(
        self,
        project_id: str,
        path: str | Path,
        *,
        adapter: str = "auto",
        profile: str = "standard",
        attach_crossref: bool = False,
    ) -> JobRecord:
        source = Path(path).resolve()
        relative = source.relative_to(self.workspace).as_posix()
        request = {
            "path": relative,
            "adapter": adapter,
            "profile": profile,
            "attach_crossref": attach_crossref,
        }

        def work() -> tuple[str, dict[str, Any], str | None]:
            from caereflex.services import inspect_path, save_case_to_store

            config = CaeReflexConfig(workspace_dir=self.workspace)
            case = inspect_path(
                source,
                adapter=adapter,
                config=config,
                attach_crossref=attach_crossref,
                profile=profile,
            )
            save_case_to_store(case, self.workspace)
            revision = self.lifecycle_store.create_revision(
                project_id,
                case.model_dump(mode="json"),
                label=f"inspection:{relative}",
                metadata={"adapter": adapter, "profile": profile},
            )
            outcome = case.inspection.status.value if hasattr(case.inspection.status, "value") else str(case.inspection.status)
            summary = {
                "status": outcome,
                "case_id": case.case_id,
                "revision_id": revision.revision_id,
                "warning_count": len(case.inspection_flags),
            }
            return outcome, summary, revision.revision_id

        return self._submit(
            kind="lifecycle.inspect",
            project_id=project_id,
            run_kind="inspection",
            request_summary=request,
            work=work,
        )

    def submit_comparison(
        self,
        project_id: str,
        baseline_revision_id: str,
        candidate_revision_id: str,
        *,
        ignore_paths: list[str] | None = None,
        max_changes: int = 200,
    ) -> JobRecord:
        request = {
            "baseline_revision_id": baseline_revision_id,
            "candidate_revision_id": candidate_revision_id,
            "ignore_paths": ignore_paths or [],
            "max_changes": max_changes,
        }

        def work() -> tuple[str, dict[str, Any], str | None]:
            comparison = compare_revisions(
                self.lifecycle_store,
                project_id,
                baseline_revision_id,
                candidate_revision_id,
                ignore_paths=ignore_paths,
                max_changes=max_changes,
            )
            return (
                "success",
                {
                    "status": "success",
                    "comparison_id": comparison.comparison_id,
                    "counts": comparison.counts,
                    "truncated": comparison.truncated,
                },
                None,
            )

        return self._submit(
            kind="lifecycle.compare",
            project_id=project_id,
            run_kind="temporal_comparison",
            request_summary=request,
            work=work,
            input_revision_id=candidate_revision_id,
        )

    def get(self, job_id: str) -> JobRecord:
        return self.job_store.get(job_id)

    def list(self, limit: int = 100, status: str | None = None) -> list[JobRecord]:
        if limit < 1 or limit > 100:
            raise ValueError("REST-facing job limit must be between 1 and 100")
        return self.job_store.list(limit, status=status)

    def shutdown(self, wait: bool = False) -> None:
        self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=True)
