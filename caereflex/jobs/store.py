"""SQLite-backed local job records for isolated inspection execution."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from caereflex.contracts import ExecutionStatus, JobRecord


class JobStoreError(RuntimeError):
    """Raised when a job record cannot be stored or retrieved."""


class JobStore:
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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    record_json TEXT NOT NULL
                )
                """
            )

    def put(self, record: JobRecord) -> JobRecord:
        status = record.status.value if hasattr(record.status, "value") else str(record.status)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, kind, status, created_at, started_at, completed_at, record_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    kind = excluded.kind,
                    status = excluded.status,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at,
                    record_json = excluded.record_json
                """,
                (
                    record.job_id,
                    record.kind,
                    status,
                    record.created_at,
                    record.started_at,
                    record.completed_at,
                    record.model_dump_json(),
                ),
            )
        return record

    def get(self, job_id: str) -> JobRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT record_json FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise JobStoreError(f"Unknown job ID: {job_id}")
        return JobRecord.model_validate_json(row["record_json"])

    def list(self, limit: int = 100, status: ExecutionStatus | str | None = None) -> list[JobRecord]:
        if limit <= 0 or limit > 1000:
            raise JobStoreError("limit must be between 1 and 1000")
        query = "SELECT record_json FROM jobs"
        parameters: list[object] = []
        if status is not None:
            query += " WHERE status = ?"
            parameters.append(status.value if hasattr(status, "value") else str(status))
        query += " ORDER BY created_at DESC LIMIT ?"
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [JobRecord.model_validate_json(row["record_json"]) for row in rows]
