"""Same-frame bounds and recorded-relation traversal for Gate 6C."""
from __future__ import annotations

import math
from typing import Iterable

from caereflex.spatial.contracts import SpatialEntity, SpatialEntityKind, SpatialRelation, SpatialRelationKind
from caereflex.spatial.query_models import (
    SpatialBoundsMode,
    SpatialQueryDiagnostic,
    SpatialQueryError,
    SpatialQueryResult,
    SpatialTraversalDirection,
)


class SpatialBoundsQueryMixin:
    @staticmethod
    def _box(minimum: Iterable[float], maximum: Iterable[float], dimensions: int):
        if dimensions not in {1, 2, 3}:
            raise SpatialQueryError("active_dimensions must be 1, 2, or 3")
        lower, upper = tuple(map(float, minimum)), tuple(map(float, maximum))
        if len(lower) != 3 or len(upper) != 3:
            raise SpatialQueryError("minimum and maximum must contain three values")
        if any(not math.isfinite(item) for item in (*lower, *upper)):
            raise SpatialQueryError("bounds values must be finite")
        if any(lower[index] > upper[index] for index in range(dimensions)):
            raise SpatialQueryError("bounds minimum must not exceed maximum")
        return lower, upper

    @staticmethod
    def _matches(entity: SpatialEntity, lower, upper, dimensions: int, mode: SpatialBoundsMode) -> bool:
        bounds = entity.bounds
        if bounds is None or bounds.active_dimensions < dimensions:
            return False
        if mode == SpatialBoundsMode.intersects:
            return all(bounds.maximum[i] >= lower[i] and bounds.minimum[i] <= upper[i] for i in range(dimensions))
        if mode == SpatialBoundsMode.contains:
            return all(bounds.minimum[i] <= lower[i] and bounds.maximum[i] >= upper[i] for i in range(dimensions))
        return all(bounds.minimum[i] >= lower[i] and bounds.maximum[i] <= upper[i] for i in range(dimensions))

    def query_bounds(
        self, graph_id: str, *, coordinate_frame_id: str, minimum: Iterable[float], maximum: Iterable[float],
        active_dimensions: int = 3, mode: SpatialBoundsMode | str = SpatialBoundsMode.intersects,
        entity_kinds: Iterable[SpatialEntityKind | str] | None = None,
        limit: int | None = None, offset: int = 0,
    ) -> SpatialQueryResult:
        limit, offset = self._page(limit, offset)
        mode = self._enum(mode, SpatialBoundsMode)
        lower, upper = self._box(minimum, maximum, active_dimensions)
        kinds = [self._enum(item, SpatialEntityKind).value for item in self._values(entity_kinds)]
        sql = "SELECT payload_json FROM spatial_entities WHERE graph_id = ? AND coordinate_frame_id = ?"
        parameters: list[object] = [graph_id, coordinate_frame_id]
        if kinds:
            sql += f" AND entity_kind IN ({','.join('?' for _ in kinds)})"
            parameters.extend(kinds)
        sql += " ORDER BY entity_id LIMIT ?"
        parameters.append(self.limits.max_scan_rows + 1)
        with self._connect() as connection:
            self._require_graph(connection, graph_id)
            if connection.execute(
                "SELECT 1 FROM spatial_coordinate_frames WHERE graph_id = ? AND frame_id = ?",
                (graph_id, coordinate_frame_id),
            ).fetchone() is None:
                raise SpatialQueryError(f"Unknown coordinate frame {coordinate_frame_id!r} in graph {graph_id!r}")
            rows = connection.execute(sql, parameters).fetchall()
        scan_limited = len(rows) > self.limits.max_scan_rows
        candidates = [SpatialEntity.model_validate_json(row[0]) for row in rows[: self.limits.max_scan_rows]]
        matches = [item for item in candidates if self._matches(item, lower, upper, active_dimensions, mode)]
        selected = matches[offset: offset + limit]
        more = scan_limited or len(matches) > offset + limit
        diagnostics = [SpatialQueryDiagnostic(
            code="CRX-SPATIAL-QUERY-LIMIT-001", message="Bounds scan reached the configured row ceiling.",
            details={"max_scan_rows": self.limits.max_scan_rows},
        )] if scan_limited else []
        return self._finish(SpatialQueryResult(
            graph_id=graph_id, operation="bounds", entities=selected,
            scanned_count=min(len(rows), self.limits.max_scan_rows), truncated=more,
            next_offset=self._next(offset, len(selected), more), diagnostics=diagnostics,
            metadata={"coordinate_frame_id": coordinate_frame_id, "minimum": list(lower), "maximum": list(upper),
                      "active_dimensions": active_dimensions, "mode": mode.value, "entity_kinds": kinds,
                      "coordinate_transforms_applied": False, "cross_frame_comparison": False},
        ))

