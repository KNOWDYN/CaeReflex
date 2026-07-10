"""Immutable, content-addressed local artefact storage.

The store never writes into inspected source directories. Payloads are addressed by
SHA-256 and metadata is held in SQLite. Existing payload files are never replaced.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from caereflex.contracts import ArtifactRecord

_URI_PREFIX = "caereflex-artifact://sha256/"


class ArtifactStoreError(RuntimeError):
    """Raised when an artefact cannot be stored or resolved safely."""


def _validate_digest(digest: str) -> str:
    normalized = digest.lower()
    if len(normalized) != 64 or any(character not in "0123456789abcdef" for character in normalized):
        raise ArtifactStoreError("Invalid SHA-256 artefact digest.")
    return normalized


class ArtifactStore:
    def __init__(self, state_root: str | Path = ".caereflex") -> None:
        self.state_root = Path(state_root).expanduser().resolve()
        self.artifact_root = self.state_root / "artifacts" / "sha256"
        self.database_path = self.state_root / "catalog.sqlite3"
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialise(self) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    digest TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    suffix TEXT NOT NULL,
                    immutable INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def uri_for_digest(digest: str) -> str:
        return f"{_URI_PREFIX}{_validate_digest(digest)}"

    @staticmethod
    def digest_from_uri(uri: str) -> str:
        if not uri.startswith(_URI_PREFIX):
            raise ArtifactStoreError("Only caereflex-artifact://sha256 URIs are supported by the local store.")
        return _validate_digest(uri[len(_URI_PREFIX):])

    @staticmethod
    def _relative_path(digest: str) -> Path:
        """Return one canonical payload path per digest, independent of media suffix."""

        normalized = _validate_digest(digest)
        return Path("artifacts") / "sha256" / normalized[:2] / normalized[2:4] / normalized

    def put_bytes(
        self,
        data: bytes,
        *,
        media_type: str = "application/octet-stream",
        suffix: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        digest = hashlib.sha256(data).hexdigest()
        relative_path = self._relative_path(digest)
        absolute_path = self.state_root / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)

        if not absolute_path.exists():
            file_descriptor, temporary_name = tempfile.mkstemp(prefix=".caereflex-artifact-", dir=str(absolute_path.parent))
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(file_descriptor, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.chmod(temporary_path, 0o444)
                except OSError:
                    pass
                try:
                    os.link(temporary_path, absolute_path)
                except FileExistsError:
                    pass
                except OSError:
                    os.replace(temporary_path, absolute_path)
            finally:
                temporary_path.unlink(missing_ok=True)

        stored_digest = self._hash_file(absolute_path)
        if stored_digest != digest:
            raise ArtifactStoreError("Stored artefact failed SHA-256 integrity verification.")

        normalized_suffix = suffix if suffix.startswith(".") or not suffix else f".{suffix}"
        record = ArtifactRecord(
            artifact_id=f"artifact_{digest[:24]}",
            digest=digest,
            uri=self.uri_for_digest(digest),
            relative_path=relative_path.as_posix(),
            media_type=media_type,
            size_bytes=len(data),
            suffix=normalized_suffix,
            immutable=True,
            metadata=metadata or {},
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO artifacts (
                    digest, artifact_id, uri, relative_path, media_type,
                    size_bytes, suffix, immutable, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.digest,
                    record.artifact_id,
                    record.uri,
                    record.relative_path,
                    record.media_type,
                    record.size_bytes,
                    record.suffix,
                    int(record.immutable),
                    record.created_at,
                    json.dumps(record.metadata, sort_keys=True),
                ),
            )
        return self.get(digest)

    def register_file(
        self,
        path: str | Path,
        *,
        media_type: str = "application/octet-stream",
        suffix: str | None = None,
        metadata: dict[str, Any] | None = None,
        max_bytes: int | None = None,
    ) -> ArtifactRecord:
        source = Path(path)
        if not source.is_file():
            raise ArtifactStoreError(f"Artefact source is not a file: {source}")
        size = source.stat().st_size
        if max_bytes is not None and size > max_bytes:
            raise ArtifactStoreError(f"Artefact exceeds the configured limit of {max_bytes} bytes.")
        return self.put_bytes(
            source.read_bytes(),
            media_type=media_type,
            suffix=source.suffix if suffix is None else suffix,
            metadata=metadata,
        )

    def get(self, digest_or_uri: str) -> ArtifactRecord:
        digest = self.digest_from_uri(digest_or_uri) if "://" in digest_or_uri else _validate_digest(digest_or_uri)
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM artifacts WHERE digest = ?", (digest,)).fetchone()
        if row is None:
            raise ArtifactStoreError(f"Unknown artefact digest: {digest}")
        return ArtifactRecord(
            artifact_id=row["artifact_id"],
            digest=row["digest"],
            uri=row["uri"],
            relative_path=row["relative_path"],
            media_type=row["media_type"],
            size_bytes=row["size_bytes"],
            suffix=row["suffix"],
            immutable=bool(row["immutable"]),
            created_at=row["created_at"],
            metadata=json.loads(row["metadata_json"]),
        )

    def resolve(self, digest_or_uri: str, *, verify: bool = True) -> Path:
        record = self.get(digest_or_uri)
        path = (self.state_root / record.relative_path).resolve()
        try:
            path.relative_to(self.artifact_root.resolve())
        except ValueError as exc:
            raise ArtifactStoreError("Artefact metadata resolved outside the configured artefact root.") from exc
        if not path.is_file():
            raise ArtifactStoreError(f"Artefact payload is missing: {record.digest}")
        if verify and self._hash_file(path) != record.digest:
            raise ArtifactStoreError("Artefact payload failed integrity verification.")
        return path

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def statistics(self) -> dict[str, int | str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count, COALESCE(SUM(size_bytes), 0) AS size_bytes FROM artifacts"
            ).fetchone()
        return {
            "state_root": str(self.state_root),
            "artifact_count": int(row["count"]),
            "size_bytes": int(row["size_bytes"]),
        }
