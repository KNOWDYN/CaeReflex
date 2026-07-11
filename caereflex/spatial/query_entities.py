"""Bounded entity queries for Gate 6C."""
from __future__ import annotations

from typing import Iterable
from caereflex.spatial.contracts import (
    SpatialDomain, SpatialEntity, SpatialEntityKind, SpatialEvidenceStatus, SpatialReviewStatus,
)
from caereflex.spatial.query_models import SpatialQueryDiagnostic, SpatialQueryError, SpatialQueryResult


class SpatialEntityQueryMixin:
    def query_entities(
        self, graph_id: str, *, entity_kinds: Iterable[SpatialEntityKind | str] | None = None,
        domains: Iterable[SpatialDomain | str] | None = None, coordinate_frame_id: str | None = None,
        topological_dimension: int | None = None, evidence_status: SpatialEvidenceStatus | str | None = None,
        review_status: SpatialReviewStatus | str | None = None, name_contains: str | None = None,
        source_path: str | None = None, limit: int | None = None, offset: int = 0,
    ) -> SpatialQueryResult:
        limit, offset = self._page(limit, offset)
        kinds = [self._enum(item, SpatialEntityKind).value for item in self._values(entity_kinds)]
        domain_values = [self._enum(item, SpatialDomain).value for item in self._values(domains)]
        sql, parameters = "SELECT payload_json FROM spatial_entities WHERE graph_id = ?", [graph_id]
        for column, values in (("entity_kind", kinds), ("domain", domain_values)):
            if values:
                sql += f" AND {column} IN ({','.join('?' for _ in values)})"
                parameters.extend(values)
        if coordinate_frame_id is not None:
            sql += " AND coordinate_frame_id = ?"
            parameters.append(coordinate_frame_id)
        if topological_dimension is not None:
            if topological_dimension not in {0, 1, 2, 3}:
                raise SpatialQueryError("topological_dimension must be between 0 and 3")
            sql += " AND topological_dimension = ?"
            parameters.append(topological_dimension)
        if evidence_status is not None:
            sql += " AND evidence_status = ?"
            parameters.append(self._enum(evidence_status, SpatialEvidenceStatus).value)
        if review_status is not None:
            sql += " AND review_status = ?"
            parameters.append(self._enum(review_status, SpatialReviewStatus).value)
        sql += " ORDER BY entity_id LIMIT ?"
        parameters.append(self.limits.max_scan_rows + 1)
        with self._connect() as connection:
            self._require_graph(connection, graph_id)
            rows = connection.execute(sql, parameters).fetchall()
        scan_limited = len(rows) > self.limits.max_scan_rows
        items = [SpatialEntity.model_validate_json(row[0]) for row in rows[: self.limits.max_scan_rows]]
        if name_contains:
            needle = name_contains.casefold()
            items = [item for item in items if needle in (item.name or "").casefold()]
        if source_path is not None:
            items = [item for item in items if item.source_path == source_path]
        selected = items[offset: offset + limit]
        more = scan_limited or len(items) > offset + limit
        diagnostics = [SpatialQueryDiagnostic(
            code="CRX-SPATIAL-QUERY-LIMIT-001", message="Entity scan reached the configured row ceiling.",
            details={"max_scan_rows": self.limits.max_scan_rows},
        )] if scan_limited else []
        return self._finish(SpatialQueryResult(
            graph_id=graph_id, operation="entities", entities=selected,
            scanned_count=min(len(rows), self.limits.max_scan_rows), truncated=more,
            next_offset=self._next(offset, len(selected), more), diagnostics=diagnostics,
            metadata={"ordering": "entity_id", "entity_kinds": kinds, "domains": domain_values,
                      "coordinate_frame_id": coordinate_frame_id, "name_contains": name_contains,
                      "source_path": source_path},
        ))

