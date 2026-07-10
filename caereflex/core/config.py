from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field


class CaeReflexConfig(BaseModel):
    workspace_dir: Path = Field(default_factory=lambda: Path.cwd())
    state_dir: Path | None = None
    max_file_size_mb: int = 25
    max_scan_depth: int = 3
    max_scan_files: int = 500
    max_request_body_mb: int = 10
    max_execution_memory_mb: int = 1024
    max_execution_result_mb: int = 10
    max_array_elements_returned: int = 10_000
    allow_nonlocal_server: bool = False
    server_api_key: str | None = None
    crossref_mailto: str | None = None
    crossref_cache_enabled: bool = True
    crossref_cache_ttl_days: int = 30

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def execution_state_dir(self) -> Path:
        return (self.state_dir or (self.workspace_dir / ".caereflex")).expanduser().resolve()

    @property
    def max_execution_memory_bytes(self) -> int:
        return self.max_execution_memory_mb * 1024 * 1024

    @property
    def max_execution_result_bytes(self) -> int:
        return self.max_execution_result_mb * 1024 * 1024
