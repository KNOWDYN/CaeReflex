"""Core graph and frame queries for Gate 6C."""
from __future__ import annotations

import json
import sqlite3
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, TypeVar

from caereflex.spatial.contracts import CoordinateFrame, SpatialGraph, SpatialEvidenceStatus, SpatialReviewStatus
from caereflex.spatial.store import SpatialStore
from caereflex.spatial.query_models import (
    SpatialQueryDiagnostic, SpatialQueryError, SpatialQueryLimits, SpatialQueryResult,
)

_E = TypeVar("_E", bound=Enum)

class SpatialQueryCore:
    """Read-only SQLite query core. Heavy arrays remain behind ArrayRef links."""

    def __init__(self, state_root: str | Path = ".caereflex", *, limits: SpatialQueryLimits | None = None) -> None:
        self.store = SpatialStore(state_root)
        self.database_path = self.store.database_path
        self.limits = limits or SpatialQueryLimits()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA query_only = ON")
        return connection

    def _page(self, limit: int | None, offset: int = 0) -> tuple[int, int]:
        resolved = self.limits.max_results if limit is None else int(limit)
        if resolved <= 0:
            raise SpatialQueryError("limit must be positive")
        if resolved > self.limits.max_results:
            raise SpatialQueryError(
                f"limit {resolved} exceeds the configured maximum {self.limits.max_results}"
            )
        if offset < 0 or offset > self.limits.max_offset:
            raise SpatialQueryError(f"offset must be between 0 and {self.limits.max_offset}")
        return resolved, int(offset)

    @staticmethod
    def _values(values: Iterable[Any] | None) -> list[str]:
        if values is None:
            return []
        return sorted({item.value if hasattr(item, "value") else str(item) for item in values})

    @staticmethod
    def _enum(value: Any, enum: type[_E]) -> _E:
        try:
            return enum(value)
        except ValueError as exc:
            raise SpatialQueryError(str(exc)) from exc

    def _require_graph(self, connection: sqlite3.Connection, graph_id: str) -> None:
        if connection.execute("SELECT 1 FROM spatial_graphs WHERE graph_id = ?", (graph_id,)).fetchone() is None:
            raise SpatialQueryError(f"Unknown spatial graph ID: {graph_id}")

    def _finish(self, result: SpatialQueryResult) -> SpatialQueryResult:
        result = SpatialQueryResult.model_validate(result.model_dump(mode="json"))
        try:
            payload = json.dumps(
                result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise SpatialQueryError(f"query result is not strict JSON: {exc}") from exc
        if len(payload) > self.limits.max_serialized_bytes:
            raise SpatialQueryError(f"serialized result exceeds {self.limits.max_serialized_bytes} bytes")
        return result

    @staticmethod
    def _next(offset: int, returned: int, more: bool) -> int | None:
        return offset + returned if more and returned else None

    def list_graphs(self, *, case_id: str | None = None, limit: int | None = None, offset: int = 0) -> SpatialQueryResult:
        limit, offset = self._page(limit, offset)
        sql, parameters = "SELECT payload_json FROM spatial_graphs", []
        if case_id is not None:
            sql += " WHERE case_id = ?"
            parameters.append(case_id)
        sql += " ORDER BY graph_id LIMIT ? OFFSET ?"
        parameters.extend([limit + 1, offset])
        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        more = len(rows) > limit
        graphs = [SpatialGraph.model_validate_json(row[0]) for row in rows[:limit]]
        return self._finish(SpatialQueryResult(
            operation="graphs", graphs=graphs, scanned_count=len(rows), truncated=more,
            next_offset=self._next(offset, len(graphs), more), metadata={"case_id": case_id, "ordering": "graph_id"},
        ))

    def describe_graph(self, graph_id: str) -> SpatialQueryResult:
        with self._connect() as connection:
            self._require_graph(connection, graph_id)
            graph = SpatialGraph.model_validate_json(connection.execute(
                "SELECT payload_json FROM spatial_graphs WHERE graph_id = ?", (graph_id,)
            ).fetchone()[0])
            frame_rows = connection.execute(
                "SELECT payload_json FROM spatial_coordinate_frames WHERE graph_id = ? ORDER BY frame_id LIMIT ?",
                (graph_id, self.limits.max_results + 1),
            ).fetchall()
            counts: dict[str, dict[str, int]] = {}
            for table, column, label in (
                ("spatial_entities", "entity_kind", "entity_kinds"),
                ("spatial_relations", "relation_kind", "relation_kinds"),
                ("spatial_array_links", "role", "array_roles"),
            ):
                rows = connection.execute(
                    f"SELECT {column}, COUNT(*) FROM {table} WHERE graph_id = ? GROUP BY {column} ORDER BY {column}",
                    (graph_id,),
                ).fetchall()
                counts[label] = {str(row[0]): int(row[1]) for row in rows}
        frames = [CoordinateFrame.model_validate_json(row[0]) for row in frame_rows[: self.limits.max_results]]
        return self._finish(SpatialQueryResult(
            graph_id=graph_id, operation="describe", graph=graph, frames=frames,
            scanned_count=len(frame_rows) + sum(len(item) for item in counts.values()),
            truncated=len(frame_rows) > self.limits.max_results,
            metadata={"statistics": self.store.statistics(graph_id), **counts,
                      "heavy_arrays_materialized": False, "coordinate_transforms_applied": False},
        ))

    def query_frames(
        self, graph_id: str, *, evidence_status: SpatialEvidenceStatus | str | None = None,
        review_status: SpatialReviewStatus | str | None = None, limit: int | None = None, offset: int = 0,
    ) -> SpatialQueryResult:
        limit, offset = self._page(limit, offset)
        sql, parameters = "SELECT payload_json FROM spatial_coordinate_frames WHERE graph_id = ?", [graph_id]
        if evidence_status is not None:
            sql += " AND evidence_status = ?"
            parameters.append(self._enum(evidence_status, SpatialEvidenceStatus).value)
        if review_status is not None:
            sql += " AND review_status = ?"
            parameters.append(self._enum(review_status, SpatialReviewStatus).value)
        sql += " ORDER BY frame_id LIMIT ? OFFSET ?"
        parameters.extend([limit + 1, offset])
        with self._connect() as connection:
            self._require_graph(connection, graph_id)
            rows = connection.execute(sql, parameters).fetchall()
        more = len(rows) > limit
        items = [CoordinateFrame.model_validate_json(row[0]) for row in rows[:limit]]
        return self._finish(SpatialQueryResult(
            graph_id=graph_id, operation="frames", frames=items, scanned_count=len(rows), truncated=more,
            next_offset=self._next(offset, len(items), more), metadata={"ordering": "frame_id"},
        ))

