"""Lazy numeric-array registration and bounded local queries.

Gate 5A deliberately supports a small, deterministic raw numeric format without
requiring NumPy. Native adapters may later register their own formats and query
providers while continuing to expose the same backend-neutral ArrayRef contract.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
from functools import reduce
from operator import mul
from pathlib import Path
from typing import Any, Iterable, Iterator

from caereflex.artifacts import ArtifactStore, ArtifactStoreError
from caereflex.contracts import ArrayRef, ArtifactLifetime
from caereflex.core.provenance import utc_now_iso


class ArrayQueryError(RuntimeError):
    """Raised when an array reference or bounded query is invalid."""


_DTYPE_FORMATS: dict[str, tuple[str, int]] = {
    "bool": ("?", 1),
    "int8": ("b", 1),
    "uint8": ("B", 1),
    "int16": ("h", 2),
    "uint16": ("H", 2),
    "int32": ("i", 4),
    "uint32": ("I", 4),
    "int64": ("q", 8),
    "uint64": ("Q", 8),
    "float32": ("f", 4),
    "float64": ("d", 8),
}

_DEFAULT_OPERATIONS = ["describe", "sample", "slice", "min", "max", "mean", "sum", "count"]


def _element_count(shape: tuple[int, ...]) -> int:
    return reduce(mul, shape, 1)


def _byte_order_prefix(byte_order: str) -> str:
    if byte_order == "little":
        return "<"
    if byte_order == "big":
        return ">"
    if byte_order == "native":
        return "="
    raise ArrayQueryError("byte_order must be 'little', 'big', or 'native'")


def _dtype(dtype: str) -> tuple[str, int]:
    try:
        return _DTYPE_FORMATS[dtype]
    except KeyError as exc:
        raise ArrayQueryError(f"Unsupported core raw-array dtype: {dtype}") from exc


class ArrayService:
    def __init__(self, state_root: str | Path = ".caereflex", *, max_elements_returned: int = 10_000) -> None:
        if max_elements_returned <= 0:
            raise ValueError("max_elements_returned must be positive")
        self.store = ArtifactStore(state_root)
        self.database_path = self.store.database_path
        self.max_elements_returned = max_elements_returned
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS array_refs (
                    array_id TEXT PRIMARY KEY,
                    artifact_digest TEXT NOT NULL,
                    ref_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (artifact_digest) REFERENCES artifacts(digest)
                )
                """
            )

    def register_numeric(
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
        backend: str = "caereflex-core",
        backend_version: str | None = None,
        storage_lifetime: ArtifactLifetime | str = ArtifactLifetime.case,
        permitted_operations: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArrayRef:
        format_character, _ = _dtype(dtype)
        prefix = _byte_order_prefix(byte_order)
        materialized = list(values)
        expected = _element_count(shape)
        if expected != len(materialized):
            raise ArrayQueryError(f"Shape {shape} requires {expected} elements; received {len(materialized)}.")
        try:
            payload = struct.pack(f"{prefix}{len(materialized)}{format_character}", *materialized)
        except (struct.error, OverflowError, TypeError) as exc:
            raise ArrayQueryError(f"Values cannot be represented as {dtype}: {exc}") from exc

        artifact = self.store.put_bytes(
            payload,
            media_type="application/vnd.caereflex.raw-array",
            suffix=".crxarr",
            metadata={"dtype": dtype, "shape": list(shape), "byte_order": byte_order},
        )
        semantic_identity = {
            "digest": artifact.digest,
            "dtype": dtype,
            "shape": list(shape),
            "source_asset_id": source_asset_id,
            "source_path": source_path,
            "association": association,
            "component_names": component_names or [],
            "quantity_evidence_ref": quantity_evidence_ref,
            "coordinate_frame_ref": coordinate_frame_ref,
            "time_index": time_index,
        }
        array_id = "array_" + hashlib.sha256(
            json.dumps(semantic_identity, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()[:24]
        operations = list(dict.fromkeys(permitted_operations or _DEFAULT_OPERATIONS))
        ref = ArrayRef(
            array_id=array_id,
            uri=artifact.uri,
            format="caereflex.raw.v1",
            shape=shape,
            dtype=dtype,
            chunks=None,
            checksum=f"sha256:{artifact.digest}",
            selection_capabilities=["flat-index", "contiguous-flat-slice", "deterministic-sample", "streaming-reduction"],
            source_asset_id=source_asset_id,
            source_path=source_path,
            association=association,
            component_names=component_names or [],
            quantity_evidence_ref=quantity_evidence_ref,
            coordinate_frame_ref=coordinate_frame_ref,
            time_index=time_index,
            byte_order=byte_order,
            backend=backend,
            backend_version=backend_version,
            storage_lifetime=storage_lifetime,
            permitted_operations=operations,
            metadata=metadata or {},
        )
        self.register_ref(ref)
        return ref

    def register_ref(self, ref: ArrayRef) -> ArrayRef:
        if not ref.array_id:
            raise ArrayQueryError("ArrayRef.array_id is required for registry storage.")
        try:
            digest = self.store.digest_from_uri(ref.uri)
            self.store.resolve(ref.uri)
        except ArtifactStoreError as exc:
            raise ArrayQueryError(f"Array artefact could not be registered: {exc}") from exc
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO array_refs (array_id, artifact_digest, ref_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(array_id) DO UPDATE SET
                    artifact_digest = excluded.artifact_digest,
                    ref_json = excluded.ref_json
                """,
                (ref.array_id, digest, ref.model_dump_json(), utc_now_iso()),
            )
        return ref

    def get(self, array_id: str) -> ArrayRef:
        with self._connect() as connection:
            row = connection.execute("SELECT ref_json FROM array_refs WHERE array_id = ?", (array_id,)).fetchone()
        if row is None:
            raise ArrayQueryError(f"Unknown array ID: {array_id}")
        return ArrayRef.model_validate_json(row["ref_json"])

    def list(self, limit: int = 100) -> list[ArrayRef]:
        if limit <= 0 or limit > 1000:
            raise ArrayQueryError("limit must be between 1 and 1000")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT ref_json FROM array_refs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [ArrayRef.model_validate_json(row["ref_json"]) for row in rows]

    def describe(self, array_id: str) -> dict[str, Any]:
        ref = self.get(array_id)
        self._require_operation(ref, "describe")
        path = self._resolve_artifact(ref)
        artifact = self.store.get(ref.uri)
        return {
            **ref.model_dump(mode="json"),
            "element_count": _element_count(ref.shape),
            "size_bytes": artifact.size_bytes,
            "artifact_id": artifact.artifact_id,
            "resolved_filename": path.name,
            "integrity_verified": True,
        }

    def slice(self, array_id: str, start: int, stop: int, step: int = 1) -> dict[str, Any]:
        ref = self.get(array_id)
        self._require_operation(ref, "slice")
        total = _element_count(ref.shape)
        if step <= 0:
            raise ArrayQueryError("step must be positive")
        normalized_start, normalized_stop, normalized_step = slice(start, stop, step).indices(total)
        indices = range(normalized_start, normalized_stop, normalized_step)
        count = len(indices)
        self._enforce_result_limit(count)
        values = self._read_indices(ref, indices)
        return {
            "array_id": array_id,
            "selection": {"start": normalized_start, "stop": normalized_stop, "step": normalized_step},
            "count": count,
            "values": values,
        }

    def sample(self, array_id: str, count: int = 100) -> dict[str, Any]:
        ref = self.get(array_id)
        self._require_operation(ref, "sample")
        total = _element_count(ref.shape)
        if count <= 0:
            raise ArrayQueryError("count must be positive")
        count = min(count, total)
        self._enforce_result_limit(count)
        if count == total:
            indices = list(range(total))
        elif count == 1:
            indices = [0]
        else:
            indices = [round(index * (total - 1) / (count - 1)) for index in range(count)]
        return {"array_id": array_id, "count": len(indices), "indices": indices, "values": self._read_indices(ref, indices)}

    def reduce(self, array_id: str, operation: str, *, component: int | None = None) -> dict[str, Any]:
        ref = self.get(array_id)
        operation = operation.lower()
        self._require_operation(ref, operation)
        if operation not in {"min", "max", "mean", "sum", "count"}:
            raise ArrayQueryError(f"Unsupported reduction: {operation}")

        component_count = ref.shape[-1] if ref.component_names and len(ref.shape) > 1 else None
        if component is not None:
            if component_count is None or component < 0 or component >= component_count:
                raise ArrayQueryError("component is outside the declared component axis")

        selected_count = 0
        total_value = 0.0
        minimum: float | int | bool | None = None
        maximum: float | int | bool | None = None
        for index, value in enumerate(self._iter_values(ref)):
            if component is not None and index % component_count != component:
                continue
            selected_count += 1
            total_value += float(value)
            minimum = value if minimum is None or value < minimum else minimum
            maximum = value if maximum is None or value > maximum else maximum

        if operation == "count":
            result: int | float | bool | None = selected_count
        elif selected_count == 0:
            result = None
        elif operation == "sum":
            result = total_value
        elif operation == "mean":
            result = total_value / selected_count
        elif operation == "min":
            result = minimum
        else:
            result = maximum
        return {
            "array_id": array_id,
            "operation": operation,
            "component": component,
            "count": selected_count,
            "value": result,
        }

    def _require_operation(self, ref: ArrayRef, operation: str) -> None:
        allowed = set(ref.permitted_operations or ref.selection_capabilities)
        if operation not in allowed:
            raise ArrayQueryError(f"Operation {operation!r} is not permitted for {ref.array_id or ref.uri}.")
        if ref.format != "caereflex.raw.v1":
            raise ArrayQueryError(f"No core query provider is registered for format {ref.format!r}.")

    def _enforce_result_limit(self, count: int) -> None:
        if count > self.max_elements_returned:
            raise ArrayQueryError(
                f"Query would return {count} elements; configured maximum is {self.max_elements_returned}."
            )

    def _resolve_artifact(self, ref: ArrayRef) -> Path:
        try:
            return self.store.resolve(ref.uri, verify=True)
        except ArtifactStoreError as exc:
            raise ArrayQueryError(f"Array artefact failed integrity or path validation: {exc}") from exc

    def _read_indices(self, ref: ArrayRef, indices: Iterable[int]) -> list[int | float | bool]:
        format_character, item_size = _dtype(ref.dtype)
        prefix = _byte_order_prefix(ref.byte_order)
        path = self._resolve_artifact(ref)
        values: list[int | float | bool] = []
        with path.open("rb") as handle:
            for index in indices:
                handle.seek(index * item_size)
                payload = handle.read(item_size)
                if len(payload) != item_size:
                    raise ArrayQueryError("Array payload ended before the declared shape.")
                values.append(struct.unpack(f"{prefix}{format_character}", payload)[0])
        return values

    def _iter_values(self, ref: ArrayRef, chunk_elements: int = 8192) -> Iterator[int | float | bool]:
        format_character, item_size = _dtype(ref.dtype)
        prefix = _byte_order_prefix(ref.byte_order)
        expected = _element_count(ref.shape)
        path = self._resolve_artifact(ref)
        consumed = 0
        with path.open("rb") as handle:
            while consumed < expected:
                count = min(chunk_elements, expected - consumed)
                payload = handle.read(count * item_size)
                if len(payload) != count * item_size:
                    raise ArrayQueryError("Array payload ended before the declared shape.")
                yield from struct.unpack(f"{prefix}{count}{format_character}", payload)
                consumed += count
            if handle.read(1):
                raise ArrayQueryError("Array payload contains data beyond the declared shape.")
