"""Versioned contracts for project, revision, run, review and temporal lifecycles."""
from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from caereflex.core.provenance import utc_now_iso

LIFECYCLE_PROTOCOL_VERSION = "caereflex.lifecycle/1.0"
TEMPORAL_COMPARISON_PROTOCOL_VERSION = "caereflex.temporal-comparison/1.0"
HUMAN_REVIEW_PROTOCOL_VERSION = "caereflex.human-review/1.0"
ASYNC_JOB_PROTOCOL_VERSION = "caereflex.async-job/1.0"


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProjectStatus(str, Enum):
    active = "active"
    archived = "archived"


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    success = "success"
    partial_success = "partial_success"
    failed = "failed"
    cancelled = "cancelled"


class ReviewTargetType(str, Enum):
    revision = "revision"
    run = "run"
    comparison = "comparison"


class ReviewDecision(str, Enum):
    acknowledged = "acknowledged"
    approved = "approved"
    approved_with_conditions = "approved_with_conditions"
    changes_requested = "changes_requested"
    rejected = "rejected"


class ChangeKind(str, Enum):
    added = "added"
    removed = "removed"
    changed = "changed"


class ProjectRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    protocol_version: str = LIFECYCLE_PROTOCOL_VERSION
    project_id: str
    name: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.active
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("project_id")
    @classmethod
    def project_prefix(cls, value: str) -> str:
        if not value.startswith("project_"):
            raise ValueError("project_id must start with project_")
        return value


class RevisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: str = LIFECYCLE_PROTOCOL_VERSION
    revision_id: str
    project_id: str
    sequence: int
    case_id: str
    case_digest: str
    snapshot_path: str
    parent_revision_id: str | None = None
    label: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("revision_id")
    @classmethod
    def revision_prefix(cls, value: str) -> str:
        if not value.startswith("revision_"):
            raise ValueError("revision_id must start with revision_")
        return value

    @field_validator("sequence")
    @classmethod
    def positive_sequence(cls, value: int) -> int:
        if value < 1:
            raise ValueError("sequence must be positive")
        return value


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    protocol_version: str = LIFECYCLE_PROTOCOL_VERSION
    run_id: str
    project_id: str
    kind: str
    status: RunStatus = RunStatus.queued
    input_revision_id: str | None = None
    result_revision_id: str | None = None
    job_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    started_at: str | None = None
    completed_at: str | None = None
    request_summary: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @field_validator("run_id")
    @classmethod
    def run_prefix(cls, value: str) -> str:
        if not value.startswith("run_"):
            raise ValueError("run_id must start with run_")
        return value


class RunEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    event_id: str
    run_id: str
    sequence: int
    status: RunStatus
    created_at: str = Field(default_factory=utc_now_iso)
    details: dict[str, Any] = Field(default_factory=dict)


class HumanReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    protocol_version: str = HUMAN_REVIEW_PROTOCOL_VERSION
    review_id: str
    project_id: str
    target_type: ReviewTargetType
    target_id: str
    reviewer_id: str
    reviewer_display_name: str | None = None
    decision: ReviewDecision
    statement: str = Field(min_length=1, max_length=10_000)
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    supersedes_review_id: str | None = None
    previous_review_digest: str | None = None
    signature: str | None = None
    signature_scheme: str | None = None
    record_digest: str | None = None

    @field_validator("review_id")
    @classmethod
    def review_prefix(cls, value: str) -> str:
        if not value.startswith("review_"):
            raise ValueError("review_id must start with review_")
        return value

    def with_digest(self) -> "HumanReviewRecord":
        payload = self.model_dump(mode="json", exclude={"record_digest"})
        return self.model_copy(update={"record_digest": canonical_digest(payload)})


class TemporalChange(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    path: str
    kind: ChangeKind
    before: Any | None = None
    after: Any | None = None

    @field_validator("path")
    @classmethod
    def json_pointer(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("change path must be an absolute JSON pointer")
        return value


class TemporalComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: str = TEMPORAL_COMPARISON_PROTOCOL_VERSION
    comparison_id: str
    project_id: str
    baseline_revision_id: str
    candidate_revision_id: str
    baseline_digest: str
    candidate_digest: str
    created_at: str = Field(default_factory=utc_now_iso)
    ignored_paths: list[str] = Field(default_factory=list)
    counts: dict[str, int]
    changes: list[TemporalChange] = Field(default_factory=list)
    truncated: bool = False
    comparison_digest: str | None = None

    @field_validator("comparison_id")
    @classmethod
    def comparison_prefix(cls, value: str) -> str:
        if not value.startswith("comparison_"):
            raise ValueError("comparison_id must start with comparison_")
        return value

    def with_digest(self) -> "TemporalComparison":
        payload = self.model_dump(mode="json", exclude={"comparison_digest"})
        return self.model_copy(update={"comparison_digest": canonical_digest(payload)})
