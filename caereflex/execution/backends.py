"""Built-in safe execution backends.

Gate 5A ships only a metadata audit backend. Native OpenFOAM, Gmsh and VTK readers
are intentionally deferred to later PRs.
"""
from __future__ import annotations

import os
import socket
import subprocess
import time
from typing import Any

from caereflex.contracts import AttemptOutcome, InspectionExecutionRequest, ParserAttempt
from caereflex.core.provenance import utc_now_iso
from caereflex.execution.context import ExecutionContext


class ManifestAuditBackend:
    backend_id = "core.manifest-audit"
    backend_version = "1.0.0"

    def execute(self, request: InspectionExecutionRequest, context: ExecutionContext) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        for relative_path in request.plan.selected_paths:
            entries.append(context.stat_source(relative_path))
        return {
            "summary": {
                "selected_path_count": len(request.plan.selected_paths),
                "entries": entries,
                "operation": request.plan.operation,
                "profile": request.plan.profile,
            }
        }


class TestExecutionBackend:
    """Deterministic fault-injection backend enabled only in test mode."""

    backend_id = "test.execution"
    backend_version = "1.0.0"

    def execute(self, request: InspectionExecutionRequest, context: ExecutionContext) -> dict[str, Any]:
        if os.environ.get("CAEREFLEX_ENABLE_TEST_BACKENDS") != "1":
            raise RuntimeError("Test execution backends are disabled.")
        mode = str(request.backend_options.get("mode", "success"))
        if mode == "sleep":
            time.sleep(float(request.backend_options.get("seconds", 1.0)))
        elif mode == "crash":
            os._exit(int(request.backend_options.get("exit_code", 23)))
        elif mode == "fail":
            raise RuntimeError(str(request.backend_options.get("message", "intentional test failure")))
        elif mode == "read":
            relative_path = str(request.backend_options["path"])
            payload = context.read_bytes(relative_path, length=int(request.backend_options.get("length", 64)))
            return {"summary": {"bytes": len(payload), "sha_prefix": payload[:8].hex()}}
        elif mode == "mutate":
            relative_path = str(request.backend_options.get("path", "input.dat"))
            path = context.resolve_source(relative_path)
            path.write_bytes(str(request.backend_options.get("content", "mutated")).encode("utf-8"))
            return {"summary": {"mutated": relative_path}}
        elif mode == "network":
            socket.socket()
        elif mode == "subprocess":
            subprocess.run(["echo", "blocked"], check=True)
        elif mode == "environment":
            key = str(request.backend_options.get("key", "CAEREFLEX_SECRET_FIXTURE"))
            return {"summary": {"key": key, "present": key in os.environ}}
        elif mode == "fallback":
            started = utc_now_iso()
            context.record_attempt(
                ParserAttempt(
                    attempt_id="attempt_test_native",
                    stage="native_decode",
                    backend_id="test.native",
                    backend_version="1.0",
                    outcome=AttemptOutcome.failed,
                    started_at=started,
                    completed_at=utc_now_iso(),
                    exception_type="FixtureDecodeError",
                    exception_message="native fixture decoder rejected the input",
                    fallback_to="test.structured",
                    information_lost=["native_topology"],
                )
            )
            context.record_attempt(
                ParserAttempt(
                    attempt_id="attempt_test_structured",
                    stage="structured_fallback",
                    backend_id="test.structured",
                    backend_version="1.0",
                    outcome=AttemptOutcome.success,
                    started_at=utc_now_iso(),
                    completed_at=utc_now_iso(),
                )
            )
            return {"summary": {"fallback_used": "test.structured"}}
        elif mode == "emit_array":
            values = request.backend_options.get("values", [0.0, 1.0, 2.0, 3.0])
            shape = tuple(request.backend_options.get("shape", [len(values)]))
            ref = context.register_numeric_array(
                values,
                dtype=str(request.backend_options.get("dtype", "float64")),
                shape=shape,
                source_asset_id="fixture_asset",
                association="field",
                component_names=list(request.backend_options.get("component_names", [])),
                metadata={"fixture": True},
            )
            return {"summary": {"array_id": ref.array_id}}
        return {"summary": {"mode": mode}}


BUILTIN_BACKENDS = {
    ManifestAuditBackend.backend_id: ManifestAuditBackend,
    TestExecutionBackend.backend_id: TestExecutionBackend,
}
