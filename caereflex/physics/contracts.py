"""Versioned deterministic physics-consistency contracts.

These records describe evidence checks only. They do not establish convergence,
validation, mesh adequacy, certification, or design safety.
"""
from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

PHYSICS_RULE_PROTOCOL_VERSION = "caereflex.physics-rule/1.0"


class RuleStatus(str, Enum):
    consistent = "consistent"
    inconsistent = "inconsistent"
    unknown = "unknown"
    not_applicable = "not_applicable"
    not_evaluated = "not_evaluated"
    blocked = "blocked"


class RuleSeverity(str, Enum):
    information = "information"
    warning = "warning"
    error = "error"


class EvidencePointer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    description: str
    value: Any | None = None
    source_path: str | None = None

    @field_validator("path")
    @classmethod
    def absolute_json_pointer(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("evidence paths must be absolute JSON pointers")
        return value


class RuleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    version: str
    title: str
    description: str
    domain: str
    applicability: str
    required_evidence: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitation: str
    default_severity: RuleSeverity = RuleSeverity.warning


class RuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    rule_id: str
    rule_version: str
    status: RuleStatus
    severity: RuleSeverity
    message: str
    evidence: list[EvidencePointer] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    remediation: str | None = None
    limitation: str
    deterministic: bool = True


class RulePackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: str
    version: str
    protocol_version: str = PHYSICS_RULE_PROTOCOL_VERSION
    title: str
    backend: str
    rule_ids: list[str]
    exclusions: list[str] = Field(default_factory=list)


class RuleEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    protocol_version: str = PHYSICS_RULE_PROTOCOL_VERSION
    pack: RulePackManifest
    case_id: str | None = None
    backend_id: str | None = None
    results: list[RuleResult]
    summary: dict[str, int]
    input_digest: str
    report_digest: str | None = None

    def with_digest(self) -> "RuleEvaluationReport":
        payload = self.model_dump(mode="json", exclude={"report_digest"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        return self.model_copy(update={"report_digest": "sha256:" + hashlib.sha256(encoded).hexdigest()})
