"""Subprocess entry point for bounded deep-inspection backends."""
from __future__ import annotations

import json
import math
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from caereflex.contracts import (
    AttemptOutcome,
    DiagnosticEvent,
    DiagnosticSeverity,
    ExecutionStatus,
    InspectionExecutionRequest,
    InspectionExecutionResult,
    ParserAttempt,
)
from caereflex.core.provenance import utc_now_iso
from caereflex.execution.context import ExecutionContext
from caereflex.execution.registry import get_execution_backend


def _deny(message: str):
    def denied(*args: Any, **kwargs: Any) -> Any:
        raise PermissionError(message)
    return denied


def _apply_python_guards(request: InspectionExecutionRequest) -> dict[str, str]:
    enforcement: dict[str, str] = {}
    if not request.policy.allow_network:
        denied_socket = _deny("Network access is disabled by the CaeReflex execution policy.")
        socket.socket = denied_socket  # type: ignore[assignment]
        socket.create_connection = denied_socket  # type: ignore[assignment]
        enforcement["network"] = "python-socket-guard"
    else:
        enforcement["network"] = "allowed"

    if not request.policy.allow_subprocess:
        denied_process = _deny("Child-process creation is disabled by the CaeReflex execution policy.")
        subprocess.Popen = denied_process  # type: ignore[assignment]
        subprocess.run = denied_process  # type: ignore[assignment]
        subprocess.call = denied_process  # type: ignore[assignment]
        subprocess.check_call = denied_process  # type: ignore[assignment]
        subprocess.check_output = denied_process  # type: ignore[assignment]
        os.system = denied_process  # type: ignore[assignment]
        os.popen = denied_process  # type: ignore[assignment]
        enforcement["subprocess"] = "python-process-guard"
    else:
        enforcement["subprocess"] = "allowed"
    return enforcement


def _apply_posix_limits(request: InspectionExecutionRequest) -> dict[str, str]:
    if not request.policy.enforce_posix_resource_limits or os.name != "posix":
        return {"resource_limits": "not-enforced-on-this-platform-or-disabled"}
    try:
        import resource

        if request.policy.max_memory_bytes is not None:
            resource.setrlimit(resource.RLIMIT_AS, (request.policy.max_memory_bytes, request.policy.max_memory_bytes))
        cpu_seconds = max(1, int(math.ceil(request.plan.budget.max_wall_time_seconds)) + 1)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        return {"resource_limits": "posix-rlimit", "cpu_seconds": str(cpu_seconds)}
    except Exception as exc:
        return {"resource_limits": f"best-effort-failed:{type(exc).__name__}"}


def run_worker(request_path: str | Path, result_path: str | Path) -> int:
    request = InspectionExecutionRequest.model_validate_json(Path(request_path).read_text(encoding="utf-8"))
    started_at = utc_now_iso()
    started_clock = time.monotonic()
    attempt_id = f"attempt_{uuid.uuid4().hex[:20]}"
    backend_version: str | None = None
    context = ExecutionContext(request=request, work_root=Path(result_path).parent / "work")
    guard_metadata = _apply_python_guards(request)
    guard_metadata.update(_apply_posix_limits(request))

    try:
        backend = get_execution_backend(request.backend_id)
        backend_version = backend.backend_version
        payload = backend.execute(request, context) or {}
        completed_at = utc_now_iso()
        elapsed = time.monotonic() - started_clock
        attempt = ParserAttempt(
            attempt_id=attempt_id,
            stage=request.plan.operation,
            backend_id=request.backend_id,
            backend_version=backend_version,
            outcome=AttemptOutcome.success,
            started_at=started_at,
            completed_at=completed_at,
            elapsed_seconds=elapsed,
            metadata={"policy_enforcement": guard_metadata},
        )
        result = InspectionExecutionResult(
            execution_id=request.execution_id,
            job_id=request.job_id,
            plugin_id=request.plan.plugin_id,
            backend_id=request.backend_id,
            backend_version=backend_version,
            status=ExecutionStatus.success,
            started_at=started_at,
            completed_at=completed_at,
            elapsed_seconds=elapsed,
            bytes_read=context.bytes_read,
            paths_accessed=context.paths_accessed,
            arrays=context.arrays,
            artifacts=context.artifacts,
            attempts=[attempt],
            diagnostics=context.diagnostics,
            metadata={"backend_result": payload, "policy_enforcement": guard_metadata},
        )
    except Exception as exc:
        completed_at = utc_now_iso()
        elapsed = time.monotonic() - started_clock
        diagnostic = DiagnosticEvent(
            code="CRX-EXEC-BACKEND-001",
            severity=DiagnosticSeverity.error,
            message=f"Execution backend {request.backend_id!r} failed: {exc}",
            parser="caereflex.execution.worker",
            details={"exception_type": type(exc).__name__},
            information_lost=["native_or_deep_inspection_result"],
        )
        attempt = ParserAttempt(
            attempt_id=attempt_id,
            stage=request.plan.operation,
            backend_id=request.backend_id,
            backend_version=backend_version,
            outcome=AttemptOutcome.failed,
            started_at=started_at,
            completed_at=completed_at,
            elapsed_seconds=elapsed,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            diagnostics=[diagnostic],
            metadata={"policy_enforcement": guard_metadata},
        )
        result = InspectionExecutionResult(
            execution_id=request.execution_id,
            job_id=request.job_id,
            plugin_id=request.plan.plugin_id,
            backend_id=request.backend_id,
            backend_version=backend_version,
            status=ExecutionStatus.failed,
            started_at=started_at,
            completed_at=completed_at,
            elapsed_seconds=elapsed,
            bytes_read=context.bytes_read,
            paths_accessed=context.paths_accessed,
            arrays=context.arrays,
            artifacts=context.artifacts,
            attempts=[attempt],
            diagnostics=[*context.diagnostics, diagnostic],
            termination_reason=str(exc),
            metadata={"policy_enforcement": guard_metadata},
        )

    destination = Path(result_path)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    os.replace(temporary, destination)
    return 0 if result.status == ExecutionStatus.success else 1


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python -m caereflex.execution.worker REQUEST.json RESULT.json", file=sys.stderr)
        return 2
    return run_worker(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    raise SystemExit(main())
