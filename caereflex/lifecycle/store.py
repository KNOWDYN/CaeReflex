"""SQLite lifecycle registry with immutable snapshots and append-only review records."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from caereflex.core.provenance import utc_now_iso
from caereflex.lifecycle.contracts import (
    HumanReviewRecord,
    ProjectRecord,
    ProjectStatus,
    ReviewDecision,
    ReviewTargetType,
    RunEvent,
    RunRecord,
    RunStatus,
    RevisionRecord,
    TemporalComparison,
)


class LifecycleStoreError(RuntimeError):
    pass


class ImmutableRecordError(LifecycleStoreError):
    pass


class InvalidTransitionError(LifecycleStoreError):
    pass


_TERMINAL_RUN_STATUSES = {
    RunStatus.success.value,
    RunStatus.partial_success.value,
    RunStatus.failed.value,
    RunStatus.cancelled.value,
}
_ALLOWED_RUN_TRANSITIONS = {
    RunStatus.queued.value: {RunStatus.running.value, RunStatus.failed.value, RunStatus.cancelled.value},
    RunStatus.running.value: _TERMINAL_RUN_STATUSES,
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


class LifecycleStore:
    def __init__(self, state_root: str | Path = ".caereflex") -> None:
        self.state_root = Path(state_root).expanduser().resolve()
        self.database_path = self.state_root / "lifecycle.sqlite3"
        self.snapshot_root = self.state_root / "revisions"
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.snapshot_root.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    revision_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    sequence INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    UNIQUE(project_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    sequence INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    UNIQUE(run_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS comparisons (
                    comparison_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    created_at TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    record_digest TEXT NOT NULL UNIQUE,
                    record_json TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS revisions_immutable_update
                BEFORE UPDATE ON revisions BEGIN SELECT RAISE(ABORT, 'revision records are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS revisions_immutable_delete
                BEFORE DELETE ON revisions BEGIN SELECT RAISE(ABORT, 'revision records are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS comparisons_immutable_update
                BEFORE UPDATE ON comparisons BEGIN SELECT RAISE(ABORT, 'comparison records are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS comparisons_immutable_delete
                BEFORE DELETE ON comparisons BEGIN SELECT RAISE(ABORT, 'comparison records are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS reviews_immutable_update
                BEFORE UPDATE ON reviews BEGIN SELECT RAISE(ABORT, 'human review records are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS reviews_immutable_delete
                BEFORE DELETE ON reviews BEGIN SELECT RAISE(ABORT, 'human review records are immutable'); END;
                """
            )

    @staticmethod
    def _bounded_limit(limit: int, maximum: int = 1000) -> int:
        if limit < 1 or limit > maximum:
            raise LifecycleStoreError(f"limit must be between 1 and {maximum}")
        return limit

    def create_project(
        self,
        name: str,
        *,
        description: str = "",
        metadata: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> ProjectRecord:
        name = name.strip()
        if not name or len(name) > 200:
            raise LifecycleStoreError("project name must contain 1 to 200 characters")
        if len(description) > 4000:
            raise LifecycleStoreError("project description exceeds 4000 characters")
        record = ProjectRecord(
            project_id=project_id or _new_id("project"),
            name=name,
            description=description,
            metadata=metadata or {},
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO projects(project_id,status,created_at,updated_at,record_json) VALUES(?,?,?,?,?)",
                    (record.project_id, record.status, record.created_at, record.updated_at, record.model_dump_json()),
                )
        except sqlite3.IntegrityError as exc:
            raise LifecycleStoreError(f"project already exists: {record.project_id}") from exc
        return record

    def get_project(self, project_id: str) -> ProjectRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT record_json FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        if row is None:
            raise LifecycleStoreError(f"unknown project ID: {project_id}")
        return ProjectRecord.model_validate_json(row["record_json"])

    def list_projects(self, limit: int = 100, status: ProjectStatus | str | None = None) -> list[ProjectRecord]:
        limit = self._bounded_limit(limit)
        query = "SELECT record_json FROM projects"
        params: list[Any] = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status.value if hasattr(status, "value") else str(status))
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [ProjectRecord.model_validate_json(row["record_json"]) for row in rows]

    def archive_project(self, project_id: str) -> ProjectRecord:
        project = self.get_project(project_id)
        if project.status == ProjectStatus.archived.value:
            return project
        with self._connect() as connection:
            active = connection.execute(
                "SELECT COUNT(*) AS count FROM runs WHERE project_id = ? AND status IN (?, ?)",
                (project_id, RunStatus.queued.value, RunStatus.running.value),
            ).fetchone()["count"]
            if active:
                raise InvalidTransitionError("project cannot be archived while runs are queued or running")
            now = utc_now_iso()
            updated = project.model_copy(update={"status": ProjectStatus.archived, "updated_at": now})
            connection.execute(
                "UPDATE projects SET status = ?, updated_at = ?, record_json = ? WHERE project_id = ?",
                (ProjectStatus.archived.value, now, updated.model_dump_json(), project_id),
            )
        return updated

    def create_revision(
        self,
        project_id: str,
        case_payload: dict[str, Any],
        *,
        label: str | None = None,
        parent_revision_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RevisionRecord:
        project = self.get_project(project_id)
        if project.status != ProjectStatus.active.value:
            raise InvalidTransitionError("new revisions require an active project")
        if not isinstance(case_payload, dict):
            raise LifecycleStoreError("case payload must be a JSON object")
        case_id = str(case_payload.get("case_id") or "").strip()
        if not case_id:
            raise LifecycleStoreError("case payload is missing case_id")
        canonical = _json(case_payload).encode("utf-8")
        digest = "sha256:" + hashlib.sha256(canonical).hexdigest()

        snapshot_path: Path | None = None
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                if parent_revision_id is not None:
                    parent_row = connection.execute(
                        "SELECT project_id FROM revisions WHERE revision_id = ?", (parent_revision_id,)
                    ).fetchone()
                    if parent_row is None:
                        raise LifecycleStoreError(f"unknown parent revision ID: {parent_revision_id}")
                    if parent_row["project_id"] != project_id:
                        raise LifecycleStoreError("parent revision belongs to another project")
                else:
                    latest = connection.execute(
                        "SELECT revision_id FROM revisions WHERE project_id = ? ORDER BY sequence DESC LIMIT 1", (project_id,)
                    ).fetchone()
                    parent_revision_id = latest["revision_id"] if latest else None
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM revisions WHERE project_id = ?", (project_id,)
                ).fetchone()["sequence"]
                revision_id = _new_id("revision")
                relative = Path("revisions") / project_id / f"{sequence:06d}_{revision_id}.json"
                snapshot_path = self.state_root / relative
                snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path = snapshot_path.with_suffix(snapshot_path.suffix + ".tmp")
                with temp_path.open("xb") as handle:
                    handle.write(canonical)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, snapshot_path)
                record = RevisionRecord(
                    revision_id=revision_id,
                    project_id=project_id,
                    sequence=sequence,
                    case_id=case_id,
                    case_digest=digest,
                    snapshot_path=relative.as_posix(),
                    parent_revision_id=parent_revision_id,
                    label=label,
                    metadata=metadata or {},
                )
                connection.execute(
                    "INSERT INTO revisions(revision_id,project_id,sequence,created_at,record_json) VALUES(?,?,?,?,?)",
                    (record.revision_id, project_id, sequence, record.created_at, record.model_dump_json()),
                )
            return record
        except Exception:
            if snapshot_path is not None and snapshot_path.exists():
                snapshot_path.unlink(missing_ok=True)
            raise

    def get_revision(self, revision_id: str) -> RevisionRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT record_json FROM revisions WHERE revision_id = ?", (revision_id,)).fetchone()
        if row is None:
            raise LifecycleStoreError(f"unknown revision ID: {revision_id}")
        return RevisionRecord.model_validate_json(row["record_json"])

    def list_revisions(self, project_id: str, limit: int = 100) -> list[RevisionRecord]:
        self.get_project(project_id)
        limit = self._bounded_limit(limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM revisions WHERE project_id = ? ORDER BY sequence DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return [RevisionRecord.model_validate_json(row["record_json"]) for row in rows]

    def load_revision_payload(self, revision_id: str) -> dict[str, Any]:
        record = self.get_revision(revision_id)
        path = (self.state_root / record.snapshot_path).resolve()
        try:
            path.relative_to(self.state_root)
        except ValueError as exc:
            raise ImmutableRecordError("revision snapshot path escaped lifecycle state root") from exc
        if not path.is_file():
            raise ImmutableRecordError(f"revision snapshot is missing: {revision_id}")
        raw = path.read_bytes()
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if digest != record.case_digest:
            raise ImmutableRecordError(f"revision snapshot digest mismatch: {revision_id}")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ImmutableRecordError("revision snapshot is not a JSON object")
        return value

    def create_run(
        self,
        project_id: str,
        kind: str,
        *,
        input_revision_id: str | None = None,
        job_id: str | None = None,
        request_summary: dict[str, Any] | None = None,
    ) -> RunRecord:
        project = self.get_project(project_id)
        if project.status != ProjectStatus.active.value:
            raise InvalidTransitionError("new runs require an active project")
        if input_revision_id is not None and self.get_revision(input_revision_id).project_id != project_id:
            raise LifecycleStoreError("input revision belongs to another project")
        record = RunRecord(
            run_id=_new_id("run"),
            project_id=project_id,
            kind=kind,
            input_revision_id=input_revision_id,
            job_id=job_id,
            request_summary=request_summary or {},
        )
        event = RunEvent(event_id=_new_id("event"), run_id=record.run_id, sequence=1, status=RunStatus.queued)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs(run_id,project_id,status,created_at,record_json) VALUES(?,?,?,?,?)",
                (record.run_id, project_id, RunStatus.queued.value, record.created_at, record.model_dump_json()),
            )
            connection.execute(
                "INSERT INTO run_events(event_id,run_id,sequence,status,created_at,details_json) VALUES(?,?,?,?,?,?)",
                (event.event_id, event.run_id, event.sequence, RunStatus.queued.value, event.created_at, "{}"),
            )
        return record

    def get_run(self, run_id: str) -> RunRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT record_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise LifecycleStoreError(f"unknown run ID: {run_id}")
        return RunRecord.model_validate_json(row["record_json"])

    def list_runs(self, project_id: str, limit: int = 100) -> list[RunRecord]:
        self.get_project(project_id)
        limit = self._bounded_limit(limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM runs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?", (project_id, limit)
            ).fetchall()
        return [RunRecord.model_validate_json(row["record_json"]) for row in rows]

    def transition_run(
        self,
        run_id: str,
        status: RunStatus | str,
        *,
        result_revision_id: str | None = None,
        result_summary: dict[str, Any] | None = None,
        error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> RunRecord:
        desired = status.value if hasattr(status, "value") else str(status)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT record_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise LifecycleStoreError(f"unknown run ID: {run_id}")
            current = RunRecord.model_validate_json(row["record_json"])
            current_status = str(current.status)
            if current_status in _TERMINAL_RUN_STATUSES:
                raise InvalidTransitionError(f"run is terminal: {current_status}")
            if desired not in _ALLOWED_RUN_TRANSITIONS.get(current_status, set()):
                raise InvalidTransitionError(f"invalid run transition: {current_status} -> {desired}")
            now = utc_now_iso()
            if result_revision_id is not None:
                revision = self.get_revision(result_revision_id)
                if revision.project_id != current.project_id:
                    raise LifecycleStoreError("result revision belongs to another project")
            updates: dict[str, Any] = {
                "status": desired,
                "result_summary": result_summary if result_summary is not None else current.result_summary,
                "error": error,
            }
            if desired == RunStatus.running.value:
                updates["started_at"] = now
            if desired in _TERMINAL_RUN_STATUSES:
                updates["completed_at"] = now
            if result_revision_id is not None:
                updates["result_revision_id"] = result_revision_id
            updated = current.model_copy(update=updates)
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM run_events WHERE run_id = ?", (run_id,)
            ).fetchone()["sequence"]
            event = RunEvent(
                event_id=_new_id("event"), run_id=run_id, sequence=sequence, status=desired, details=details or {}
            )
            connection.execute(
                "UPDATE runs SET status = ?, record_json = ? WHERE run_id = ?",
                (desired, updated.model_dump_json(), run_id),
            )
            connection.execute(
                "INSERT INTO run_events(event_id,run_id,sequence,status,created_at,details_json) VALUES(?,?,?,?,?,?)",
                (event.event_id, run_id, sequence, desired, event.created_at, _json(event.details)),
            )
        return updated

    def list_run_events(self, run_id: str) -> list[RunEvent]:
        self.get_run(run_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id,run_id,sequence,status,created_at,details_json FROM run_events WHERE run_id = ? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        return [
            RunEvent(
                event_id=row["event_id"],
                run_id=row["run_id"],
                sequence=row["sequence"],
                status=row["status"],
                created_at=row["created_at"],
                details=json.loads(row["details_json"]),
            )
            for row in rows
        ]

    def save_comparison(self, comparison: TemporalComparison) -> TemporalComparison:
        self.get_project(comparison.project_id)
        for revision_id in (comparison.baseline_revision_id, comparison.candidate_revision_id):
            if self.get_revision(revision_id).project_id != comparison.project_id:
                raise LifecycleStoreError("comparison revision belongs to another project")
        record = comparison if comparison.comparison_digest else comparison.with_digest()
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO comparisons(comparison_id,project_id,created_at,record_json) VALUES(?,?,?,?)",
                    (record.comparison_id, record.project_id, record.created_at, record.model_dump_json()),
                )
        except sqlite3.IntegrityError as exc:
            raise LifecycleStoreError(f"comparison already exists: {record.comparison_id}") from exc
        return record

    def get_comparison(self, comparison_id: str) -> TemporalComparison:
        with self._connect() as connection:
            row = connection.execute("SELECT record_json FROM comparisons WHERE comparison_id = ?", (comparison_id,)).fetchone()
        if row is None:
            raise LifecycleStoreError(f"unknown comparison ID: {comparison_id}")
        return TemporalComparison.model_validate_json(row["record_json"])

    def list_comparisons(self, project_id: str, limit: int = 100) -> list[TemporalComparison]:
        self.get_project(project_id)
        limit = self._bounded_limit(limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM comparisons WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return [TemporalComparison.model_validate_json(row["record_json"]) for row in rows]

    def _validate_review_target(self, project_id: str, target_type: str, target_id: str) -> None:
        if target_type == ReviewTargetType.revision.value:
            target_project = self.get_revision(target_id).project_id
        elif target_type == ReviewTargetType.run.value:
            target_project = self.get_run(target_id).project_id
        elif target_type == ReviewTargetType.comparison.value:
            target_project = self.get_comparison(target_id).project_id
        else:
            raise LifecycleStoreError(f"unsupported review target type: {target_type}")
        if target_project != project_id:
            raise LifecycleStoreError("review target belongs to another project")

    def add_review(
        self,
        project_id: str,
        target_type: ReviewTargetType | str,
        target_id: str,
        *,
        reviewer_id: str,
        decision: ReviewDecision | str,
        statement: str,
        reviewer_display_name: str | None = None,
        evidence_refs: list[str] | None = None,
        supersedes_review_id: str | None = None,
        signature: str | None = None,
        signature_scheme: str | None = None,
    ) -> HumanReviewRecord:
        self.get_project(project_id)
        target_type_value = target_type.value if hasattr(target_type, "value") else str(target_type)
        decision_value = decision.value if hasattr(decision, "value") else str(decision)
        self._validate_review_target(project_id, target_type_value, target_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT record_digest FROM reviews WHERE project_id = ? AND target_type = ? AND target_id = ? ORDER BY created_at DESC, review_id DESC LIMIT 1",
                (project_id, target_type_value, target_id),
            ).fetchone()
            if supersedes_review_id is not None:
                superseded = connection.execute(
                    "SELECT project_id,target_type,target_id FROM reviews WHERE review_id = ?", (supersedes_review_id,)
                ).fetchone()
                if superseded is None:
                    raise LifecycleStoreError(f"unknown superseded review ID: {supersedes_review_id}")
                if (superseded["project_id"], superseded["target_type"], superseded["target_id"]) != (
                    project_id,
                    target_type_value,
                    target_id,
                ):
                    raise LifecycleStoreError("superseded review targets a different record")
            record = HumanReviewRecord(
                review_id=_new_id("review"),
                project_id=project_id,
                target_type=target_type_value,
                target_id=target_id,
                reviewer_id=reviewer_id,
                reviewer_display_name=reviewer_display_name,
                decision=decision_value,
                statement=statement,
                evidence_refs=evidence_refs or [],
                supersedes_review_id=supersedes_review_id,
                previous_review_digest=previous["record_digest"] if previous else None,
                signature=signature,
                signature_scheme=signature_scheme,
            ).with_digest()
            connection.execute(
                "INSERT INTO reviews(review_id,project_id,target_type,target_id,created_at,record_digest,record_json) VALUES(?,?,?,?,?,?,?)",
                (
                    record.review_id,
                    project_id,
                    target_type_value,
                    target_id,
                    record.created_at,
                    record.record_digest,
                    record.model_dump_json(),
                ),
            )
        return record

    def get_review(self, review_id: str) -> HumanReviewRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT record_json FROM reviews WHERE review_id = ?", (review_id,)).fetchone()
        if row is None:
            raise LifecycleStoreError(f"unknown review ID: {review_id}")
        record = HumanReviewRecord.model_validate_json(row["record_json"])
        expected = record.model_copy(update={"record_digest": None}).with_digest().record_digest
        if record.record_digest != expected:
            raise ImmutableRecordError(f"human review digest mismatch: {review_id}")
        return record

    def list_reviews(
        self,
        project_id: str,
        *,
        target_type: ReviewTargetType | str | None = None,
        target_id: str | None = None,
        limit: int = 100,
    ) -> list[HumanReviewRecord]:
        self.get_project(project_id)
        limit = self._bounded_limit(limit)
        query = "SELECT record_json FROM reviews WHERE project_id = ?"
        params: list[Any] = [project_id]
        if target_type is not None:
            query += " AND target_type = ?"
            params.append(target_type.value if hasattr(target_type, "value") else str(target_type))
        if target_id is not None:
            query += " AND target_id = ?"
            params.append(target_id)
        query += " ORDER BY created_at DESC, review_id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [HumanReviewRecord.model_validate_json(row["record_json"]) for row in rows]
