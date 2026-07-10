"""SQLite catalog cache for incremental CaeReflex discovery."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pydantic import BaseModel, Field

from caereflex.contracts import CaseManifest
from caereflex.core.provenance import utc_now_iso


class ManifestDiff(BaseModel):
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)


class CatalogStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS manifests (
                    root_uri TEXT PRIMARY KEY,
                    manifest_id TEXT NOT NULL,
                    signature TEXT,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def save(self, manifest: CaseManifest) -> None:
        payload = manifest.model_dump_json()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO manifests(root_uri, manifest_id, signature, created_at, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(root_uri) DO UPDATE SET
                    manifest_id=excluded.manifest_id,
                    signature=excluded.signature,
                    created_at=excluded.created_at,
                    payload=excluded.payload
                """,
                (manifest.root_uri, manifest.manifest_id, manifest.signature, utc_now_iso(), payload),
            )

    def load(self, root_uri: str) -> CaseManifest | None:
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM manifests WHERE root_uri = ?", (root_uri,)).fetchone()
        if not row:
            return None
        try:
            return CaseManifest.model_validate_json(row[0])
        except (ValueError, json.JSONDecodeError):
            return None

    def clear(self) -> int:
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM manifests").fetchone()[0]
            connection.execute("DELETE FROM manifests")
        return int(count)

    @staticmethod
    def diff(previous: CaseManifest | None, current: CaseManifest) -> ManifestDiff:
        if previous is None:
            return ManifestDiff(added=[entry.path for entry in current.entries])
        old = {entry.path: entry for entry in previous.entries}
        new = {entry.path: entry for entry in current.entries}
        added = sorted(new.keys() - old.keys())
        removed = sorted(old.keys() - new.keys())
        changed: list[str] = []
        unchanged: list[str] = []
        for path in sorted(new.keys() & old.keys()):
            before = old[path]
            after = new[path]
            if (before.size_bytes, before.modified_ns, before.role, before.format_hint) != (
                after.size_bytes,
                after.modified_ns,
                after.role,
                after.format_hint,
            ):
                changed.append(path)
            else:
                unchanged.append(path)
        return ManifestDiff(added=added, removed=removed, changed=changed, unchanged=unchanged)
