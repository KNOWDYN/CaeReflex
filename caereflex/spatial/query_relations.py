"""Bounded relation and ArrayRef-link queries for Gate 6C."""
from __future__ import annotations

from typing import Iterable
from caereflex.spatial.contracts import (
    SpatialArrayLink, SpatialArrayRole, SpatialEvidenceStatus, SpatialRelation,
    SpatialRelationKind, SpatialReviewStatus,
)
from caereflex.spatial.query_models import SpatialQueryError, SpatialQueryResult, SpatialTraversalDirection


class SpatialRelationQueryMixin:
    def query_relations(
        self, graph_id: str, *, entity_id: str | None = None,
        relation_kinds: Iterable[SpatialRelationKind | str] | None = None,
        direction: SpatialTraversalDirection | str = SpatialTraversalDirection.both,
        evidence_status: SpatialEvidenceStatus | str | None = None,
        review_status: SpatialReviewStatus | str | None = None,
        limit: int | None = None, offset: int = 0,
    ) -> SpatialQueryResult:
        limit, offset = self._page(limit, offset)
        direction = self._enum(direction, SpatialTraversalDirection)
        kinds = [self._enum(item, SpatialRelationKind).value for item in self._values(relation_kinds)]
        sql, parameters = "SELECT payload_json FROM spatial_relations WHERE graph_id = ?", [graph_id]
        if entity_id is not None:
            clause = {
                SpatialTraversalDirection.outgoing: "(source_entity_id = ? OR (directed = 0 AND target_entity_id = ?))",
                SpatialTraversalDirection.incoming: "(target_entity_id = ? OR (directed = 0 AND source_entity_id = ?))",
                SpatialTraversalDirection.both: "(source_entity_id = ? OR target_entity_id = ?)",
            }[direction]
            sql += f" AND {clause}"
            parameters.extend([entity_id, entity_id])
        if kinds:
            sql += f" AND relation_kind IN ({','.join('?' for _ in kinds)})"
            parameters.extend(kinds)
        if evidence_status is not None:
            sql += " AND evidence_status = ?"
            parameters.append(self._enum(evidence_status, SpatialEvidenceStatus).value)
        if review_status is not None:
            sql += " AND review_status = ?"
            parameters.append(self._enum(review_status, SpatialReviewStatus).value)
        sql += " ORDER BY relation_id LIMIT ? OFFSET ?"
        parameters.extend([limit + 1, offset])
        with self._connect() as connection:
            self._require_graph(connection, graph_id)
            if entity_id is not None and connection.execute(
                "SELECT 1 FROM spatial_entities WHERE graph_id = ? AND entity_id = ?", (graph_id, entity_id)
            ).fetchone() is None:
                raise SpatialQueryError(f"Unknown entity ID in graph {graph_id}: {entity_id}")
            rows = connection.execute(sql, parameters).fetchall()
        more = len(rows) > limit
        items = [SpatialRelation.model_validate_json(row[0]) for row in rows[:limit]]
        return self._finish(SpatialQueryResult(
            graph_id=graph_id, operation="relations", relations=items, scanned_count=len(rows), truncated=more,
            next_offset=self._next(offset, len(items), more),
            metadata={"ordering": "relation_id", "entity_id": entity_id, "relation_kinds": kinds,
                      "direction": direction.value, "inference_performed": False},
        ))

    def query_array_links(
        self, graph_id: str, *, owner_entity_id: str | None = None, owner_frame_id: str | None = None,
        roles: Iterable[SpatialArrayRole | str] | None = None, limit: int | None = None, offset: int = 0,
    ) -> SpatialQueryResult:
        if owner_entity_id is not None and owner_frame_id is not None:
            raise SpatialQueryError("select either an entity owner or a frame owner")
        limit, offset = self._page(limit, offset)
        role_values = [self._enum(item, SpatialArrayRole).value for item in self._values(roles)]
        sql, parameters = "SELECT payload_json FROM spatial_array_links WHERE graph_id = ?", [graph_id]
        for column, value in (("owner_entity_id", owner_entity_id), ("owner_frame_id", owner_frame_id)):
            if value is not None:
                sql += f" AND {column} = ?"
                parameters.append(value)
        if role_values:
            sql += f" AND role IN ({','.join('?' for _ in role_values)})"
            parameters.extend(role_values)
        sql += " ORDER BY link_id LIMIT ? OFFSET ?"
        parameters.extend([limit + 1, offset])
        with self._connect() as connection:
            self._require_graph(connection, graph_id)
            rows = connection.execute(sql, parameters).fetchall()
        more = len(rows) > limit
        items = [SpatialArrayLink.model_validate_json(row[0]) for row in rows[:limit]]
        return self._finish(SpatialQueryResult(
            graph_id=graph_id, operation="array_links", array_links=items, scanned_count=len(rows), truncated=more,
            next_offset=self._next(offset, len(items), more),
            metadata={"ordering": "link_id", "owner_entity_id": owner_entity_id,
                      "owner_frame_id": owner_frame_id, "roles": role_values,
                      "heavy_arrays_materialized": False},
        ))
