"""Bounded worker context supplied to deep-inspection backends."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from caereflex.arrays import ArrayService
from caereflex.contracts import ArrayRef, ArtifactRecord, DiagnosticEvent, InspectionExecutionRequest, ParserAttempt


class ExecutionContextError(RuntimeError):
    """Raised when a backend exceeds its declared execution scope or budget."""


@dataclass
class ExecutionContext:
    request: InspectionExecutionRequest
    work_root: Path
    array_service: ArrayService = field(init=False)
    bytes_read: int = 0
    paths_accessed: list[str] = field(default_factory=list)
    arrays: list[ArrayRef] = field(default_factory=list)
    artifacts: list[ArtifactRecord] = field(default_factory=list)
    attempts: list[ParserAttempt] = field(default_factory=list)
    diagnostics: list[DiagnosticEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.source_root = Path(self.request.source_root).expanduser().resolve()
        self.work_root = self.work_root.resolve()
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.array_service = ArrayService(
            self.request.artifact_root,
            max_elements_returned=max(1, self.request.plan.budget.max_array_elements_returned),
        )
        self._selected = [self._resolve_unchecked(path) for path in self.request.plan.selected_paths]

    def _resolve_unchecked(self, relative_path: str) -> Path:
        candidate = (self.source_root / relative_path).resolve()
        try:
            candidate.relative_to(self.source_root)
        except ValueError as exc:
            raise ExecutionContextError(f"Selected path escapes the source root: {relative_path}") from exc
        return candidate

    def resolve_source(self, relative_path: str) -> Path:
        candidate = self._resolve_unchecked(relative_path)
        allowed = False
        for selected in self._selected:
            if candidate == selected:
                allowed = True
                break
            if selected.is_dir():
                try:
                    candidate.relative_to(selected)
                    allowed = True
                    break
                except ValueError:
                    pass
        if not allowed:
            raise ExecutionContextError(f"Backend attempted to access an unplanned path: {relative_path}")
        display = candidate.relative_to(self.source_root).as_posix()
        if display not in self.paths_accessed:
            self.paths_accessed.append(display)
        return candidate

    def stat_source(self, relative_path: str) -> dict[str, Any]:
        path = self.resolve_source(relative_path)
        stat = path.stat()
        return {
            "path": path.relative_to(self.source_root).as_posix(),
            "is_file": path.is_file(),
            "is_dir": path.is_dir(),
            "size_bytes": stat.st_size if path.is_file() else None,
            "modified_ns": stat.st_mtime_ns,
        }

    def read_bytes(self, relative_path: str, *, offset: int = 0, length: int | None = None) -> bytes:
        path = self.resolve_source(relative_path)
        if not path.is_file():
            raise ExecutionContextError(f"Source path is not a file: {relative_path}")
        if offset < 0 or (length is not None and length < 0):
            raise ExecutionContextError("offset and length must be non-negative")
        remaining = self.request.plan.budget.max_bytes_read - self.bytes_read
        requested = remaining if length is None else length
        if requested > remaining:
            raise ExecutionContextError("Backend read would exceed InspectionBudget.max_bytes_read")
        with path.open("rb") as handle:
            handle.seek(offset)
            payload = handle.read(requested)
        self.bytes_read += len(payload)
        return payload

    def record_attempt(self, attempt: ParserAttempt) -> ParserAttempt:
        """Append one ordered native/fallback parser attempt to the execution ledger."""

        self.attempts.append(attempt)
        self.diagnostics.extend(attempt.diagnostics)
        return attempt

    def register_numeric_array(
        self,
        values: Iterable[int | float | bool],
        *,
        dtype: str,
        shape: tuple[int, ...],
        source_asset_id: str | None = None,
        source_path: str | None = None,
        association: str | None = None,
        component_names: list[str] | None = None,
        quantity_evidence_ref: str | None = None,
        coordinate_frame_ref: str | None = None,
        time_index: str | float | int | None = None,
        byte_order: str = "little",
        metadata: dict[str, Any] | None = None,
    ) -> ArrayRef:
        ref = self.array_service.register_numeric(
            values,
            dtype=dtype,
            shape=shape,
            source_asset_id=source_asset_id,
            source_path=source_path,
            association=association,
            component_names=component_names,
            quantity_evidence_ref=quantity_evidence_ref,
            coordinate_frame_ref=coordinate_frame_ref,
            time_index=time_index,
            byte_order=byte_order,
            backend=self.request.backend_id,
            backend_version=None,
            metadata=metadata,
        )
        self.arrays.append(ref)
        artifact = self.array_service.store.get(ref.uri)
        if artifact.artifact_id not in {item.artifact_id for item in self.artifacts}:
            self.artifacts.append(artifact)
        return ref
