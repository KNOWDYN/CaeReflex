"""Parent-side executor for isolated deep-inspection backends."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from caereflex.contracts import (
    AttemptOutcome,
    CaseManifest,
    DiagnosticEvent,
    DiagnosticSeverity,
    ExecutionPolicy,
    ExecutionStatus,
    InspectionExecutionRequest,
    InspectionExecutionResult,
    InspectionPlan,
    JobRecord,
    ParserAttempt,
)
from caereflex.core.provenance import utc_now_iso
from caereflex.jobs import JobStore


class InspectionExecutionError(RuntimeError):
    """Raised when an execution request cannot be started safely."""


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _snapshot_sources(
    source_root: Path,
    selected_paths: list[str],
    *,
    max_files: int,
    max_hash_bytes: int,
) -> tuple[dict[str, dict[str, Any]], bool]:
    records: dict[str, dict[str, Any]] = {}
    complete = True
    hashed_bytes = 0
    candidates: list[Path] = []
    for relative_path in selected_paths:
        candidate = (source_root / relative_path).resolve()
        try:
            candidate.relative_to(source_root)
        except ValueError as exc:
            raise InspectionExecutionError(f"Selected path escapes the source root: {relative_path}") from exc
        if candidate.is_dir():
            for child in sorted(candidate.rglob("*")):
                if child.is_file() or child.is_symlink():
                    candidates.append(child)
        else:
            candidates.append(candidate)

    for candidate in candidates:
        if len(records) >= max_files:
            complete = False
            break
        try:
            relative = candidate.relative_to(source_root).as_posix()
        except ValueError:
            complete = False
            continue
        if candidate.is_symlink():
            stat = candidate.lstat()
            records[relative] = {
                "kind": "symlink",
                "target": os.readlink(candidate),
                "size_bytes": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
            }
            continue
        if not candidate.is_file():
            continue
        stat = candidate.stat()
        row: dict[str, Any] = {
            "kind": "file",
            "size_bytes": stat.st_size,
            "modified_ns": stat.st_mtime_ns,
        }
        if hashed_bytes + stat.st_size <= max_hash_bytes:
            row["sha256"] = _file_digest(candidate)
            hashed_bytes += stat.st_size
        else:
            row["sha256"] = None
            complete = False
        records[relative] = row
    return records, complete


def _sanitized_environment(policy: ExecutionPolicy) -> dict[str, str]:
    if not policy.sanitize_environment:
        environment = dict(os.environ)
    else:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in set(policy.environment_allowlist)
        }
    environment.update(
        {
            "PYTHONNOUSERSITE": "1",
            "PYTHONHASHSEED": "0",
            "CAEREFLEX_WORKER": "1",
        }
    )
    if os.environ.get("CAEREFLEX_ENABLE_TEST_BACKENDS") == "1":
        environment["CAEREFLEX_ENABLE_TEST_BACKENDS"] = "1"
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        environment.pop(key, None)
    return environment


def _terminal_result(
    request: InspectionExecutionRequest,
    *,
    status: ExecutionStatus,
    code: str,
    message: str,
    outcome: AttemptOutcome,
    started_at: str,
    elapsed_seconds: float,
    worker_exit_code: int | None,
    log_path: Path,
) -> InspectionExecutionResult:
    completed_at = utc_now_iso()
    diagnostic = DiagnosticEvent(
        code=code,
        severity=DiagnosticSeverity.error,
        message=message,
        parser="caereflex.execution.executor",
        details={"worker_log": log_path.name},
        information_lost=["deep_inspection_result"],
    )
    attempt = ParserAttempt(
        attempt_id=f"attempt_{uuid.uuid4().hex[:20]}",
        stage=request.plan.operation,
        backend_id=request.backend_id,
        outcome=outcome,
        started_at=started_at,
        completed_at=completed_at,
        elapsed_seconds=elapsed_seconds,
        exception_message=message,
        diagnostics=[diagnostic],
    )
    return InspectionExecutionResult(
        execution_id=request.execution_id,
        job_id=request.job_id,
        plugin_id=request.plan.plugin_id,
        backend_id=request.backend_id,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        elapsed_seconds=elapsed_seconds,
        attempts=[attempt],
        diagnostics=[diagnostic],
        termination_reason=message,
        worker_exit_code=worker_exit_code,
        metadata={"worker_log": log_path.name},
    )


def execute_inspection_plan(
    manifest: CaseManifest,
    plan: InspectionPlan,
    *,
    backend_id: str,
    source_root: str | Path,
    state_root: str | Path = ".caereflex",
    backend_options: dict[str, Any] | None = None,
    policy: ExecutionPolicy | None = None,
) -> InspectionExecutionResult:
    source_root_path = Path(source_root).expanduser().resolve()
    if not source_root_path.exists() or not source_root_path.is_dir():
        raise InspectionExecutionError("source_root must be an existing directory")
    state_root_path = Path(state_root).expanduser().resolve()
    state_root_path.mkdir(parents=True, exist_ok=True)
    policy = policy or ExecutionPolicy()
    job_id = f"job_{uuid.uuid4().hex[:24]}"
    execution_id = f"execution_{uuid.uuid4().hex[:24]}"
    job_directory = state_root_path / "jobs" / job_id
    job_directory.mkdir(parents=True, exist_ok=False)
    request_path = job_directory / "request.json"
    result_path = job_directory / "result.json"
    log_path = job_directory / "worker.log"

    request = InspectionExecutionRequest(
        execution_id=execution_id,
        job_id=job_id,
        backend_id=backend_id,
        backend_options=backend_options or {},
        source_root=str(source_root_path),
        artifact_root=str(state_root_path),
        manifest=manifest,
        plan=plan,
        policy=policy,
    )
    request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")

    jobs = JobStore(state_root_path)
    job = JobRecord(
        job_id=job_id,
        kind="inspection-execution",
        status=ExecutionStatus.pending,
        request_summary={
            "execution_id": execution_id,
            "plugin_id": plan.plugin_id,
            "backend_id": backend_id,
            "profile": plan.profile,
            "selected_path_count": len(plan.selected_paths),
        },
    )
    jobs.put(job)

    before, before_complete = _snapshot_sources(
        source_root_path,
        plan.selected_paths,
        max_files=plan.budget.max_files,
        max_hash_bytes=policy.max_source_hash_bytes,
    )
    started_at = utc_now_iso()
    started_clock = time.monotonic()
    job.status = ExecutionStatus.running
    job.started_at = started_at
    jobs.put(job)

    command = [sys.executable, "-m", "caereflex.execution.worker", str(request_path), str(result_path)]
    with log_path.open("wb") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=str(job_directory),
            env=_sanitized_environment(policy),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        try:
            process.wait(timeout=plan.budget.max_wall_time_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            elapsed = time.monotonic() - started_clock
            result = _terminal_result(
                request,
                status=ExecutionStatus.timed_out,
                code="CRX-EXEC-TIMEOUT-001",
                message=f"Execution exceeded {plan.budget.max_wall_time_seconds} seconds and was terminated.",
                outcome=AttemptOutcome.timed_out,
                started_at=started_at,
                elapsed_seconds=elapsed,
                worker_exit_code=process.returncode,
                log_path=log_path,
            )
        else:
            elapsed = time.monotonic() - started_clock
            if not result_path.exists():
                result = _terminal_result(
                    request,
                    status=ExecutionStatus.crashed,
                    code="CRX-EXEC-CRASH-001",
                    message=f"Execution worker exited with code {process.returncode} without a result payload.",
                    outcome=AttemptOutcome.crashed,
                    started_at=started_at,
                    elapsed_seconds=elapsed,
                    worker_exit_code=process.returncode,
                    log_path=log_path,
                )
            elif result_path.stat().st_size > policy.max_result_bytes:
                result = _terminal_result(
                    request,
                    status=ExecutionStatus.failed,
                    code="CRX-EXEC-RESULT-001",
                    message="Execution result exceeded the configured serialized-result limit.",
                    outcome=AttemptOutcome.failed,
                    started_at=started_at,
                    elapsed_seconds=elapsed,
                    worker_exit_code=process.returncode,
                    log_path=log_path,
                )
            else:
                try:
                    result = InspectionExecutionResult.model_validate_json(result_path.read_text(encoding="utf-8"))
                    result.worker_exit_code = process.returncode
                except Exception as exc:
                    result = _terminal_result(
                        request,
                        status=ExecutionStatus.failed,
                        code="CRX-EXEC-RESULT-001",
                        message=f"Execution result could not be validated: {exc}",
                        outcome=AttemptOutcome.failed,
                        started_at=started_at,
                        elapsed_seconds=elapsed,
                        worker_exit_code=process.returncode,
                        log_path=log_path,
                    )

    after, after_complete = _snapshot_sources(
        source_root_path,
        plan.selected_paths,
        max_files=plan.budget.max_files,
        max_hash_bytes=policy.max_source_hash_bytes,
    )
    result.source_snapshot_complete = before_complete and after_complete
    if before != after:
        result.source_mutation_detected = True
        diagnostic = DiagnosticEvent(
            code="CRX-EXEC-SOURCE-MUTATION-001",
            severity=DiagnosticSeverity.error,
            message="One or more inspected source files changed during isolated execution.",
            parser="caereflex.execution.executor",
            details={
                "changed_paths": sorted(set(before) | set(after)),
                "snapshot_complete": result.source_snapshot_complete,
            },
        )
        result.diagnostics.append(diagnostic)
        result.status = ExecutionStatus.failed
        result.termination_reason = "source mutation detected"
    elif not result.source_snapshot_complete:
        result.diagnostics.append(
            DiagnosticEvent(
                code="CRX-EXEC-SNAPSHOT-PARTIAL-001",
                severity=DiagnosticSeverity.warning,
                message="Source immutability was checked by metadata for some files because the hashing budget was exhausted.",
                parser="caereflex.execution.executor",
            )
        )

    result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    job.status = result.status
    job.completed_at = result.completed_at or utc_now_iso()
    job.result_summary = {
        "execution_id": result.execution_id,
        "backend_id": result.backend_id,
        "status": result.status,
        "array_count": len(result.arrays),
        "artifact_count": len(result.artifacts),
        "diagnostic_count": len(result.diagnostics),
        "result_path": str(result_path.relative_to(state_root_path)),
    }
    job.diagnostics = result.diagnostics
    jobs.put(job)
    return result
