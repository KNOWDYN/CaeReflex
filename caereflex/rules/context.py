"""Evidence context shared by deterministic physics-consistency rules."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from caereflex.arrays import ArrayQueryError, ArrayService
from caereflex.contracts import ArrayRef
from caereflex.core.models import ReflexCase
from caereflex.rules.contracts import RuleBlockedError, RuleEvidenceRef

_NO_DEFAULT = object()
_MISSING = object()


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _compact_preview(value: Any) -> Any:
    """Keep evidence compact while retaining its exact JSON-pointer source path."""
    if isinstance(value, list):
        if len(value) <= 32:
            return [_compact_preview(item) for item in value]
        return {
            "collection_type": "list",
            "count": len(value),
            "preview": [_compact_preview(item) for item in value[:8]],
        }
    if isinstance(value, tuple):
        return _compact_preview(list(value))
    if isinstance(value, dict):
        keys = sorted(str(key) for key in value)
        if len(keys) <= 32:
            return {key: _compact_preview(value[key]) for key in keys}
        return {
            "collection_type": "object",
            "count": len(keys),
            "keys_preview": keys[:16],
        }
    return value


class RuleEvaluationContext:
    def __init__(self, case: ReflexCase, *, state_root: str | Path | None = None) -> None:
        self.case = case
        self.payload = case.model_dump(mode="json")
        self.state_root = Path(state_root).expanduser().resolve() if state_root is not None else None
        self._arrays: dict[str, ArrayRef] = {}
        self._array_pointers: dict[str, str] = {}
        for index, item in enumerate(case.array_references):
            if not isinstance(item, dict) or not item.get("array_id"):
                continue
            ref = ArrayRef.model_validate(item)
            array_id = str(ref.array_id)
            self._arrays[array_id] = ref
            self._array_pointers[array_id] = f"/array_references/{index}"
        self._array_service: ArrayService | None = None

    def resolve(self, pointer: str, default: Any = _NO_DEFAULT) -> Any:
        if pointer == "":
            return self.payload
        if not pointer.startswith("/"):
            raise ValueError("rule evidence paths must use absolute JSON pointers")
        current: Any = self.payload
        try:
            for raw in pointer[1:].split("/"):
                token = _unescape(raw)
                if isinstance(current, list):
                    current = current[int(token)]
                elif isinstance(current, dict):
                    current = current[token]
                else:
                    raise KeyError(token)
        except (KeyError, IndexError, ValueError, TypeError):
            if default is _NO_DEFAULT:
                raise KeyError(pointer)
            return default
        return current

    def exists(self, pointer: str) -> bool:
        return self.resolve(pointer, _MISSING) is not _MISSING

    def evidence(
        self,
        pointer: str,
        *,
        source_path: str | None = None,
        value: Any = _MISSING,
        evidence_state: str = "explicit",
        note: str | None = None,
    ) -> RuleEvidenceRef:
        resolved = self.resolve(pointer, None) if value is _MISSING else value
        return RuleEvidenceRef(
            path=pointer,
            source_path=source_path,
            value=_compact_preview(resolved),
            evidence_state=evidence_state,
            note=note,
        )

    @property
    def native_openfoam(self) -> dict[str, Any] | None:
        value = self.resolve("/metadata/native_openfoam", None)
        return value if isinstance(value, dict) else None

    def array_ref(self, array_id: str | None) -> ArrayRef | None:
        return self._arrays.get(str(array_id)) if array_id else None

    def array_pointer(self, array_id: str | None) -> str:
        if not array_id or str(array_id) not in self._array_pointers:
            raise RuleBlockedError(f"ArrayRef {array_id!r} has no exact ReflexCase evidence path")
        return self._array_pointers[str(array_id)]

    def require_array_ref(self, array_id: str | None, *, evidence_path: str) -> ArrayRef:
        ref = self.array_ref(array_id)
        if ref is None:
            raise RuleBlockedError(
                f"ArrayRef {array_id!r} referenced at {evidence_path} is absent from ReflexCase.array_references"
            )
        return ref

    def array_service(self) -> ArrayService:
        if self.state_root is None:
            raise RuleBlockedError(
                "The rule requires registered lazy-array evidence, but no CaeReflex state root was supplied"
            )
        if self._array_service is None:
            self._array_service = ArrayService(self.state_root)
        return self._array_service

    def array_reduce(self, array_id: str, operation: str) -> dict[str, Any]:
        try:
            return self.array_service().reduce(array_id, operation)
        except ArrayQueryError as exc:
            raise RuleBlockedError(f"Array evidence {array_id!r} could not be verified: {exc}") from exc

    def array_slice(self, array_id: str, start: int, stop: int) -> dict[str, Any]:
        try:
            return self.array_service().slice(array_id, start, stop)
        except ArrayQueryError as exc:
            raise RuleBlockedError(f"Array evidence {array_id!r} could not be verified: {exc}") from exc

    def array_query_evidence(
        self,
        array_id: str,
        *,
        operation: str,
        value: Any,
        component: int | None = None,
    ) -> RuleEvidenceRef:
        detail: dict[str, Any] = {"operation": operation, "value": value}
        if component is not None:
            detail["component"] = component
        return self.evidence(
            self.array_pointer(array_id),
            value=detail,
            evidence_state="derived",
            note=f"bounded ArrayRef query on {array_id}",
        )


__all__ = ["RuleEvaluationContext"]
