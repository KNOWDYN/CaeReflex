"""SQLite persistence for compact Gate 6A spatial graphs.

Only contracts and references are stored here. Numerical coordinates, connectivity,
transforms and fields remain in the content-addressed ArrayRef registry.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from caereflex.contracts import CONTRACT_VERSION
from caereflex.core.provenance import utc_now_iso
from caereflex.spatial.contracts import (
    CoordinateFrame,
    SpatialArrayLink,
    SpatialEntity,
    SpatialGraph,
    SpatialGraphRef,
    SpatialGraphSnapshot,
    SpatialRelation,
)


class SpatialStoreError(RuntimeError):
    """Raised when a spatial graph cannot be persisted or read safely."""


class SpatialStore:
    def __init__(self, state_root: str | Path = ".caereflex") -> None:
        self.state_root = Path(state_root).expanduser().resolve()
        self.database_path = self.state_root / "catalog.sqlite3"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS spatial_graphs (
                    graph_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    graph_version TEXT NOT NULL,
                    contract_version TEXT NOT NULL,
                    name TEXT,
                    source_manifest_id TEXT,
                    default_frame_id TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS spatial_coordinate_frames (
                    graph_id TEXT NOT NULL,
                    frame_id TEXT NOT NULL,
                    parent_frame_id TEXT,
                    evidence_status TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (graph_id, frame_id),
                    FOREIGN KEY (graph_id)
                        REFERENCES spatial_graphs(graph_id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (graph_id, parent_frame_id)
                        REFERENCES spatial_coordinate_frames(graph_id, frame_id)
                        ON DELETE RESTRICT
                        DEFERRABLE INITIALLY DEFERRED
                );

                CREATE TABLE IF NOT EXISTS spatial_entities (
                    graph_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    entity_kind TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    topological_dimension INTEGER,
                    embedding_dimension INTEGER,
                    coordinate_frame_id TEXT,
                    evidence_status TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (graph_id, entity_id),
                    FOREIGN KEY (graph_id)
                        REFERENCES spatial_graphs(graph_id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (graph_id, coordinate_frame_id)
                        REFERENCES spatial_coordinate_frames(graph_id, frame_id)
                        ON DELETE RESTRICT
                        DEFERRABLE INITIALLY DEFERRED
                );

                CREATE TABLE IF NOT EXISTS spatial_relations (
                    graph_id TEXT NOT NULL,
                    relation_id TEXT NOT NULL,
                    relation_kind TEXT NOT NULL,
                    source_entity_id TEXT NOT NULL,
                    target_entity_id TEXT NOT NULL,
                    directed INTEGER NOT NULL,
                    evidence_status TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (graph_id, relation_id),
                    FOREIGN KEY (graph_id)
                        REFERENCES spatial_graphs(graph_id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (graph_id, source_entity_id)
                        REFERENCES spatial_entities(graph_id, entity_id)
                        ON DELETE CASCADE
                        DEFERRABLE INITIALLY DEFERRED,
                    FOREIGN KEY (graph_id, target_entity_id)
                        REFERENCES spatial_entities(graph_id, entity_id)
                        ON DELETE CASCADE
                        DEFERRABLE INITIALLY DEFERRED
                );

                CREATE TABLE IF NOT EXISTS spatial_array_links (
                    graph_id TEXT NOT NULL,
                    link_id TEXT NOT NULL,
                    array_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    owner_entity_id TEXT,
                    owner_frame_id TEXT,
                    coordinate_frame_id TEXT,
                    evidence_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (graph_id, link_id),
                    CHECK (
                        (owner_entity_id IS NOT NULL AND owner_frame_id IS NULL)
                        OR
                        (owner_entity_id IS NULL AND owner_frame_id IS NOT NULL)
                    ),
                    FOREIGN KEY (graph_id)
                        REFERENCES spatial_graphs(graph_id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (graph_id, owner_entity_id)
                        REFERENCES spatial_entities(graph_id, entity_id)
                        ON DELETE CASCADE
                        DEFERRABLE INITIALLY DEFERRED,
                    FOREIGN KEY (graph_id, owner_frame_id)
                        REFERENCES spatial_coordinate_frames(graph_id, frame_id)
                        ON DELETE CASCADE
                        DEFERRABLE INITIALLY DEFERRED,
                    FOREIGN KEY (graph_id, coordinate_frame_id)
                        REFERENCES spatial_coordinate_frames(graph_id, frame_id)
                        ON DELETE RESTRICT
                        DEFERRABLE INITIALLY DEFERRED
                );

                CREATE INDEX IF NOT EXISTS idx_spatial_graph_case
                    ON spatial_graphs(case_id);
                CREATE INDEX IF NOT EXISTS idx_spatial_entity_kind
                    ON spatial_entities(graph_id, entity_kind);
                CREATE INDEX IF NOT EXISTS idx_spatial_relation_endpoints
                    ON spatial_relations(graph_id, source_entity_id, target_entity_id);
                CREATE INDEX IF NOT EXISTS idx_spatial_array_id
                    ON spatial_array_links(array_id);
                """
            )

    @staticmethod
    def store_uri(graph_id: str) -> str:
        return f"caereflex-spatial://sqlite/{graph_id}"

    def _require_graph(self, connection: sqlite3.Connection, graph_id: str) -> None:
        row = connection.execute(
            "SELECT 1 FROM spatial_graphs WHERE graph_id = ?", (graph_id,)
        ).fetchone()
        if row is None:
            raise SpatialStoreError(f"Unknown spatial graph ID: {graph_id}")

    def _require_frame(
        self,
        connection: sqlite3.Connection,
        graph_id: str,
        frame_id: str,
    ) -> None:
        row = connection.execute(
            """
            SELECT 1 FROM spatial_coordinate_frames
            WHERE graph_id = ? AND frame_id = ?
            """,
            (graph_id, frame_id),
        ).fetchone()
        if row is None:
            raise SpatialStoreError(
                f"Unknown coordinate frame {frame_id!r} in graph {graph_id!r}"
            )

    def _require_entity(
        self,
        connection: sqlite3.Connection,
        graph_id: str,
        entity_id: str,
    ) -> None:
        row = connection.execute(
            """
            SELECT 1 FROM spatial_entities
            WHERE graph_id = ? AND entity_id = ?
            """,
            (graph_id, entity_id),
        ).fetchone()
        if row is None:
            raise SpatialStoreError(
                f"Unknown spatial entity {entity_id!r} in graph {graph_id!r}"
            )

    def _require_registered_array(
        self,
        connection: sqlite3.Connection,
        array_id: str,
    ) -> None:
        table = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'array_refs'
            """
        ).fetchone()
        if table is None:
            raise SpatialStoreError(
                "ArrayRef registry is absent; register the array before creating a spatial link"
            )
        row = connection.execute(
            "SELECT 1 FROM array_refs WHERE array_id = ?", (array_id,)
        ).fetchone()
        if row is None:
            raise SpatialStoreError(f"Unknown ArrayRef ID: {array_id}")

    def _insert_graph(
        self,
        connection: sqlite3.Connection,
        graph: SpatialGraph,
    ) -> None:
        if graph.contract_version != CONTRACT_VERSION:
            raise SpatialStoreError(
                f"Spatial graph contract {graph.contract_version!r} does not match "
                f"runtime contract {CONTRACT_VERSION!r}"
            )
        try:
            connection.execute(
                """
                INSERT INTO spatial_graphs (
                    graph_id, case_id, graph_version, contract_version, name,
                    source_manifest_id, default_frame_id, status,
                    created_at, updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    graph.graph_id,
                    graph.case_id,
                    graph.graph_version,
                    graph.contract_version,
                    graph.name,
                    graph.source_manifest_id,
                    graph.default_coordinate_frame_id,
                    str(graph.status),
                    graph.created_at,
                    graph.updated_at,
                    graph.model_dump_json(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise SpatialStoreError(
                f"Spatial graph {graph.graph_id!r} already exists"
            ) from exc

    def create_graph(self, graph: SpatialGraph) -> SpatialGraph:
        if graph.default_coordinate_frame_id is not None:
            raise SpatialStoreError(
                "Create the graph before assigning its default coordinate frame"
            )
        with self._connect() as connection:
            self._insert_graph(connection, graph)
        return graph

    def get_graph(self, graph_id: str) -> SpatialGraph:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM spatial_graphs WHERE graph_id = ?",
                (graph_id,),
            ).fetchone()
        if row is None:
            raise SpatialStoreError(f"Unknown spatial graph ID: {graph_id}")
        return SpatialGraph.model_validate_json(row["payload_json"])

    def list_graphs(self, case_id: str | None = None) -> list[SpatialGraph]:
        query = "SELECT payload_json FROM spatial_graphs"
        parameters: tuple[object, ...] = ()
        if case_id is not None:
            query += " WHERE case_id = ?"
            parameters = (case_id,)
        query += " ORDER BY graph_id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [SpatialGraph.model_validate_json(row["payload_json"]) for row in rows]

    def _parent_map(
        self,
        connection: sqlite3.Connection,
        graph_id: str,
        proposed: CoordinateFrame | None = None,
    ) -> dict[str, str | None]:
        rows = connection.execute(
            """
            SELECT frame_id, parent_frame_id
            FROM spatial_coordinate_frames
            WHERE graph_id = ?
            """,
            (graph_id,),
        ).fetchall()
        parents = {row["frame_id"]: row["parent_frame_id"] for row in rows}
        if proposed is not None:
            parents[proposed.frame_id] = proposed.parent_frame_id
        return parents

    @staticmethod
    def _check_parent_cycles(parents: dict[str, str | None]) -> None:
        for frame_id in parents:
            seen: set[str] = set()
            current: str | None = frame_id
            while current is not None:
                if current in seen:
                    raise SpatialStoreError("Coordinate-frame parent cycle detected")
                seen.add(current)
                current = parents.get(current)

    def _put_frame(
        self,
        connection: sqlite3.Connection,
        graph_id: str,
        frame: CoordinateFrame,
    ) -> None:
        self._require_graph(connection, graph_id)
        if frame.parent_frame_id is not None:
            self._require_frame(connection, graph_id, frame.parent_frame_id)
        self._check_parent_cycles(self._parent_map(connection, graph_id, frame))
        connection.execute(
            """
            INSERT INTO spatial_coordinate_frames (
                graph_id, frame_id, parent_frame_id, evidence_status,
                review_status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(graph_id, frame_id) DO UPDATE SET
                parent_frame_id = excluded.parent_frame_id,
                evidence_status = excluded.evidence_status,
                review_status = excluded.review_status,
                payload_json = excluded.payload_json
            """,
            (
                graph_id,
                frame.frame_id,
                frame.parent_frame_id,
                str(frame.evidence_status),
                str(frame.review_status),
                frame.model_dump_json(),
            ),
        )

    def put_frame(self, graph_id: str, frame: CoordinateFrame) -> CoordinateFrame:
        with self._connect() as connection:
            self._put_frame(connection, graph_id, frame)
        return frame

    def set_default_frame(self, graph_id: str, frame_id: str | None) -> SpatialGraph:
        with self._connect() as connection:
            self._require_graph(connection, graph_id)
            if frame_id is not None:
                self._require_frame(connection, graph_id, frame_id)
            row = connection.execute(
                "SELECT payload_json FROM spatial_graphs WHERE graph_id = ?",
                (graph_id,),
            ).fetchone()
            graph = SpatialGraph.model_validate_json(row["payload_json"])
            graph.default_coordinate_frame_id = frame_id
            graph.updated_at = utc_now_iso()
            connection.execute(
                """
                UPDATE spatial_graphs
                SET default_frame_id = ?, updated_at = ?, payload_json = ?
                WHERE graph_id = ?
                """,
                (frame_id, graph.updated_at, graph.model_dump_json(), graph_id),
            )
        return graph

    def get_frame(self, graph_id: str, frame_id: str) -> CoordinateFrame:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM spatial_coordinate_frames
                WHERE graph_id = ? AND frame_id = ?
                """,
                (graph_id, frame_id),
            ).fetchone()
        if row is None:
            raise SpatialStoreError(
                f"Unknown coordinate frame {frame_id!r} in graph {graph_id!r}"
            )
        return CoordinateFrame.model_validate_json(row["payload_json"])

    def list_frames(self, graph_id: str) -> list[CoordinateFrame]:
        with self._connect() as connection:
            self._require_graph(connection, graph_id)
            rows = connection.execute(
                """
                SELECT payload_json FROM spatial_coordinate_frames
                WHERE graph_id = ? ORDER BY frame_id
                """,
                (graph_id,),
            ).fetchall()
        return [CoordinateFrame.model_validate_json(row["payload_json"]) for row in rows]

    def _put_entity(
        self,
        connection: sqlite3.Connection,
        graph_id: str,
        entity: SpatialEntity,
    ) -> None:
        self._require_graph(connection, graph_id)
        if entity.coordinate_frame_id is not None:
            self._require_frame(connection, graph_id, entity.coordinate_frame_id)
        connection.execute(
            """
            INSERT INTO spatial_entities (
                graph_id, entity_id, entity_kind, domain,
                topological_dimension, embedding_dimension, coordinate_frame_id,
                evidence_status, review_status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(graph_id, entity_id) DO UPDATE SET
                entity_kind = excluded.entity_kind,
                domain = excluded.domain,
                topological_dimension = excluded.topological_dimension,
                embedding_dimension = excluded.embedding_dimension,
                coordinate_frame_id = excluded.coordinate_frame_id,
                evidence_status = excluded.evidence_status,
                review_status = excluded.review_status,
                payload_json = excluded.payload_json
            """,
            (
                graph_id,
                entity.entity_id,
                str(entity.entity_kind),
                str(entity.domain),
                entity.topological_dimension,
                entity.embedding_dimension,
                entity.coordinate_frame_id,
                str(entity.evidence_status),
                str(entity.review_status),
                entity.model_dump_json(),
            ),
        )

    def put_entity(self, graph_id: str, entity: SpatialEntity) -> SpatialEntity:
        with self._connect() as connection:
            self._put_entity(connection, graph_id, entity)
        return entity

    def get_entity(self, graph_id: str, entity_id: str) -> SpatialEntity:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM spatial_entities
                WHERE graph_id = ? AND entity_id = ?
                """,
                (graph_id, entity_id),
            ).fetchone()
        if row is None:
            raise SpatialStoreError(
                f"Unknown spatial entity {entity_id!r} in graph {graph_id!r}"
            )
        return SpatialEntity.model_validate_json(row["payload_json"])

    def list_entities(
        self,
        graph_id: str,
        *,
        entity_kind: str | None = None,
    ) -> list[SpatialEntity]:
        query = """
            SELECT payload_json FROM spatial_entities
            WHERE graph_id = ?
        """
        parameters: list[object] = [graph_id]
        if entity_kind is not None:
            query += " AND entity_kind = ?"
            parameters.append(entity_kind)
        query += " ORDER BY entity_id"
        with self._connect() as connection:
            self._require_graph(connection, graph_id)
            rows = connection.execute(query, parameters).fetchall()
        return [SpatialEntity.model_validate_json(row["payload_json"]) for row in rows]

    def _put_relation(
        self,
        connection: sqlite3.Connection,
        graph_id: str,
        relation: SpatialRelation,
    ) -> None:
        self._require_graph(connection, graph_id)
        self._require_entity(connection, graph_id, relation.source_entity_id)
        self._require_entity(connection, graph_id, relation.target_entity_id)
        connection.execute(
            """
            INSERT INTO spatial_relations (
                graph_id, relation_id, relation_kind,
                source_entity_id, target_entity_id, directed,
                evidence_status, review_status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(graph_id, relation_id) DO UPDATE SET
                relation_kind = excluded.relation_kind,
                source_entity_id = excluded.source_entity_id,
                target_entity_id = excluded.target_entity_id,
                directed = excluded.directed,
                evidence_status = excluded.evidence_status,
                review_status = excluded.review_status,
                payload_json = excluded.payload_json
            """,
            (
                graph_id,
                relation.relation_id,
                str(relation.relation_kind),
                relation.source_entity_id,
                relation.target_entity_id,
                int(relation.directed),
                str(relation.evidence_status),
                str(relation.review_status),
                relation.model_dump_json(),
            ),
        )

    def put_relation(self, graph_id: str, relation: SpatialRelation) -> SpatialRelation:
        with self._connect() as connection:
            self._put_relation(connection, graph_id, relation)
        return relation

    def get_relation(self, graph_id: str, relation_id: str) -> SpatialRelation:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM spatial_relations
                WHERE graph_id = ? AND relation_id = ?
                """,
                (graph_id, relation_id),
            ).fetchone()
        if row is None:
            raise SpatialStoreError(
                f"Unknown spatial relation {relation_id!r} in graph {graph_id!r}"
            )
        return SpatialRelation.model_validate_json(row["payload_json"])

    def list_relations(
        self,
        graph_id: str,
        *,
        entity_id: str | None = None,
    ) -> list[SpatialRelation]:
        query = """
            SELECT payload_json FROM spatial_relations
            WHERE graph_id = ?
        """
        parameters: list[object] = [graph_id]
        if entity_id is not None:
            query += " AND (source_entity_id = ? OR target_entity_id = ?)"
            parameters.extend([entity_id, entity_id])
        query += " ORDER BY relation_id"
        with self._connect() as connection:
            self._require_graph(connection, graph_id)
            rows = connection.execute(query, parameters).fetchall()
        return [SpatialRelation.model_validate_json(row["payload_json"]) for row in rows]

    def _put_array_link(
        self,
        connection: sqlite3.Connection,
        graph_id: str,
        link: SpatialArrayLink,
        *,
        require_registered_array: bool,
    ) -> None:
        self._require_graph(connection, graph_id)
        if link.owner_entity_id is not None:
            self._require_entity(connection, graph_id, link.owner_entity_id)
        if link.owner_frame_id is not None:
            self._require_frame(connection, graph_id, link.owner_frame_id)
        if link.coordinate_frame_id is not None:
            self._require_frame(connection, graph_id, link.coordinate_frame_id)
        if require_registered_array:
            self._require_registered_array(connection, link.array_id)
        connection.execute(
            """
            INSERT INTO spatial_array_links (
                graph_id, link_id, array_id, role,
                owner_entity_id, owner_frame_id, coordinate_frame_id,
                evidence_status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(graph_id, link_id) DO UPDATE SET
                array_id = excluded.array_id,
                role = excluded.role,
                owner_entity_id = excluded.owner_entity_id,
                owner_frame_id = excluded.owner_frame_id,
                coordinate_frame_id = excluded.coordinate_frame_id,
                evidence_status = excluded.evidence_status,
                payload_json = excluded.payload_json
            """,
            (
                graph_id,
                link.link_id,
                link.array_id,
                str(link.role),
                link.owner_entity_id,
                link.owner_frame_id,
                link.coordinate_frame_id,
                str(link.evidence_status),
                link.model_dump_json(),
            ),
        )

    def put_array_link(
        self,
        graph_id: str,
        link: SpatialArrayLink,
        *,
        require_registered_array: bool = True,
    ) -> SpatialArrayLink:
        with self._connect() as connection:
            self._put_array_link(
                connection,
                graph_id,
                link,
                require_registered_array=require_registered_array,
            )
        return link

    def list_array_links(self, graph_id: str) -> list[SpatialArrayLink]:
        with self._connect() as connection:
            self._require_graph(connection, graph_id)
            rows = connection.execute(
                """
                SELECT payload_json FROM spatial_array_links
                WHERE graph_id = ? ORDER BY link_id
                """,
                (graph_id,),
            ).fetchall()
        return [SpatialArrayLink.model_validate_json(row["payload_json"]) for row in rows]

    def put_snapshot(
        self,
        snapshot: SpatialGraphSnapshot,
        *,
        replace: bool = False,
        require_registered_arrays: bool = True,
    ) -> SpatialGraphRef:
        graph = snapshot.graph
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if replace:
                connection.execute(
                    "DELETE FROM spatial_graphs WHERE graph_id = ?", (graph.graph_id,)
                )
            graph_without_default = graph.model_copy(
                update={"default_coordinate_frame_id": None}
            )
            self._insert_graph(connection, graph_without_default)

            pending = {item.frame_id: item for item in snapshot.coordinate_frames}
            inserted: set[str] = set()
            while pending:
                progressed = False
                for frame_id in sorted(list(pending)):
                    frame = pending[frame_id]
                    if frame.parent_frame_id is None or frame.parent_frame_id in inserted:
                        self._put_frame(connection, graph.graph_id, frame)
                        inserted.add(frame_id)
                        del pending[frame_id]
                        progressed = True
                if not progressed:
                    raise SpatialStoreError(
                        "Coordinate frames could not be ordered by parent relationship"
                    )

            for entity in sorted(snapshot.entities, key=lambda item: item.entity_id):
                self._put_entity(connection, graph.graph_id, entity)
            for relation in sorted(snapshot.relations, key=lambda item: item.relation_id):
                self._put_relation(connection, graph.graph_id, relation)
            for link in sorted(snapshot.array_links, key=lambda item: item.link_id):
                self._put_array_link(
                    connection,
                    graph.graph_id,
                    link,
                    require_registered_array=require_registered_arrays,
                )

            final_graph = graph.model_copy(update={"updated_at": utc_now_iso()})
            connection.execute(
                """
                UPDATE spatial_graphs
                SET default_frame_id = ?, status = ?, updated_at = ?, payload_json = ?
                WHERE graph_id = ?
                """,
                (
                    final_graph.default_coordinate_frame_id,
                    str(final_graph.status),
                    final_graph.updated_at,
                    final_graph.model_dump_json(),
                    final_graph.graph_id,
                ),
            )
        return self.graph_ref(graph.graph_id)

    def snapshot(self, graph_id: str) -> SpatialGraphSnapshot:
        return SpatialGraphSnapshot(
            graph=self.get_graph(graph_id),
            coordinate_frames=self.list_frames(graph_id),
            entities=self.list_entities(graph_id),
            relations=self.list_relations(graph_id),
            array_links=self.list_array_links(graph_id),
        )

    def graph_ref(self, graph_id: str) -> SpatialGraphRef:
        graph = self.get_graph(graph_id)
        counts = self.statistics(graph_id)
        return SpatialGraphRef(
            graph_id=graph.graph_id,
            store_uri=self.store_uri(graph.graph_id),
            graph_version=graph.graph_version,
            contract_version=graph.contract_version,
            default_coordinate_frame_id=graph.default_coordinate_frame_id,
            frame_count=counts["frame_count"],
            entity_count=counts["entity_count"],
            relation_count=counts["relation_count"],
            array_link_count=counts["array_link_count"],
            updated_at=graph.updated_at,
        )

    def statistics(self, graph_id: str) -> dict[str, int | str]:
        with self._connect() as connection:
            self._require_graph(connection, graph_id)
            frame_count = connection.execute(
                "SELECT COUNT(*) FROM spatial_coordinate_frames WHERE graph_id = ?",
                (graph_id,),
            ).fetchone()[0]
            entity_count = connection.execute(
                "SELECT COUNT(*) FROM spatial_entities WHERE graph_id = ?",
                (graph_id,),
            ).fetchone()[0]
            relation_count = connection.execute(
                "SELECT COUNT(*) FROM spatial_relations WHERE graph_id = ?",
                (graph_id,),
            ).fetchone()[0]
            array_link_count = connection.execute(
                "SELECT COUNT(*) FROM spatial_array_links WHERE graph_id = ?",
                (graph_id,),
            ).fetchone()[0]
        return {
            "graph_id": graph_id,
            "frame_count": int(frame_count),
            "entity_count": int(entity_count),
            "relation_count": int(relation_count),
            "array_link_count": int(array_link_count),
        }

    def validate_integrity(self) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        return [
            {
                "table": str(row[0]),
                "rowid": str(row[1]),
                "parent": str(row[2]),
                "foreign_key_index": str(row[3]),
            }
            for row in rows
        ]

    def delete_graph(self, graph_id: str) -> int:
        with self._connect() as connection:
            result = connection.execute(
                "DELETE FROM spatial_graphs WHERE graph_id = ?", (graph_id,)
            )
        return int(result.rowcount)

    def export_snapshot_json(self, graph_id: str, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            self.snapshot(graph_id).model_dump_json(indent=2),
            encoding="utf-8",
        )
        return destination
