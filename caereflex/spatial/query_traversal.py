"""Recorded-relation traversal for Gate 6C."""
from __future__ import annotations

from typing import Iterable
from caereflex.spatial.contracts import SpatialEntity, SpatialRelation, SpatialRelationKind
from caereflex.spatial.query_models import (
    SpatialQueryDiagnostic, SpatialQueryError, SpatialQueryResult, SpatialTraversalDirection,
)


class SpatialTraversalQueryMixin:
    def neighbours(
        self, graph_id: str, seed_entity_id: str, *,
        relation_kinds: Iterable[SpatialRelationKind | str] | None = None,
        direction: SpatialTraversalDirection | str = SpatialTraversalDirection.both,
        max_depth: int = 1, include_seed: bool = False, limit: int | None = None,
    ) -> SpatialQueryResult:
        limit, _ = self._page(limit, 0)
        if max_depth <= 0:
            raise SpatialQueryError("max_depth must be positive")
        if max_depth > self.limits.max_depth:
            raise SpatialQueryError(
                f"max_depth {max_depth} exceeds the configured maximum {self.limits.max_depth}"
            )
        direction = self._enum(direction, SpatialTraversalDirection)
        kinds = [self._enum(item, SpatialRelationKind).value for item in self._values(relation_kinds)]
        visited, frontier = {seed_entity_id}, [seed_entity_id]
        depth_by_entity, relation_by_id = {seed_entity_id: 0}, {}
        scanned, truncated = 0, False
        with self._connect() as connection:
            self._require_graph(connection, graph_id)
            if connection.execute(
                "SELECT 1 FROM spatial_entities WHERE graph_id = ? AND entity_id = ?", (graph_id, seed_entity_id)
            ).fetchone() is None:
                raise SpatialQueryError(f"Unknown seed entity ID in graph {graph_id}: {seed_entity_id}")
            for depth in range(1, max_depth + 1):
                if not frontier:
                    break
                next_frontier = set()
                for current in sorted(frontier):
                    clause = {
                        SpatialTraversalDirection.outgoing: "(source_entity_id = ? OR (directed = 0 AND target_entity_id = ?))",
                        SpatialTraversalDirection.incoming: "(target_entity_id = ? OR (directed = 0 AND source_entity_id = ?))",
                        SpatialTraversalDirection.both: "(source_entity_id = ? OR target_entity_id = ?)",
                    }[direction]
                    sql = f"SELECT payload_json FROM spatial_relations WHERE graph_id = ? AND {clause}"
                    parameters: list[object] = [graph_id, current, current]
                    if kinds:
                        sql += f" AND relation_kind IN ({','.join('?' for _ in kinds)})"
                        parameters.extend(kinds)
                    sql += " ORDER BY relation_id"
                    for row in connection.execute(sql, parameters).fetchall():
                        scanned += 1
                        if scanned > self.limits.max_relations_scanned:
                            truncated = True
                            break
                        relation = SpatialRelation.model_validate_json(row[0])
                        relation_by_id.setdefault(relation.relation_id, relation)
                        neighbour = relation.target_entity_id if relation.source_entity_id == current else relation.source_entity_id
                        if neighbour not in visited:
                            if len(visited) - 1 >= limit:
                                truncated = True
                                break
                            visited.add(neighbour)
                            depth_by_entity[neighbour] = depth
                            next_frontier.add(neighbour)
                    if scanned > self.limits.max_relations_scanned or len(visited) - 1 >= limit:
                        break
                frontier = sorted(next_frontier)
                if scanned > self.limits.max_relations_scanned or len(visited) - 1 >= limit:
                    break
            selected_ids = sorted(
                visited if include_seed else visited - {seed_entity_id},
                key=lambda item: (depth_by_entity[item], item),
            )[:limit]
            entities = []
            for entity_id in selected_ids:
                row = connection.execute(
                    "SELECT payload_json FROM spatial_entities WHERE graph_id = ? AND entity_id = ?",
                    (graph_id, entity_id),
                ).fetchone()
                if row is None:
                    raise SpatialQueryError(f"Traversal resolved absent entity {entity_id!r}")
                entities.append(SpatialEntity.model_validate_json(row[0]))
        relations = sorted(relation_by_id.values(), key=lambda item: item.relation_id)
        if len(relations) > limit:
            relations, truncated = relations[:limit], True
        diagnostics = [SpatialQueryDiagnostic(
            code="CRX-SPATIAL-QUERY-LIMIT-001", message="Neighbour traversal reached the relation-scan ceiling.",
            details={"max_relations_scanned": self.limits.max_relations_scanned},
        )] if scanned > self.limits.max_relations_scanned else []
        return self._finish(SpatialQueryResult(
            graph_id=graph_id, operation="neighbours", entities=entities, relations=relations,
            scanned_count=min(scanned, self.limits.max_relations_scanned), truncated=truncated, diagnostics=diagnostics,
            metadata={"seed_entity_id": seed_entity_id, "include_seed": include_seed, "relation_kinds": kinds,
                      "direction": direction.value, "max_depth": max_depth,
                      "depth_by_entity": {item: depth_by_entity[item] for item in selected_ids},
                      "recorded_relations_only": True, "adjacency_inferred": False,
                      "coordinate_transforms_applied": False},
        ))
