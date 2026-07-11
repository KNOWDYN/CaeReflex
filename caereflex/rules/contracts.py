"""Versioned contracts for deterministic physics-consistency rules.

The protocol records what was checked, the exact evidence paths used, why a rule could
or could not be evaluated, and the limitations that prevent an evidence check from
being misrepresented as engineering validation.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RULE_PROTOCOL_VERSION = "caereflex.physics-rule/1.0"


class RuleEvaluationStatus(str, Enum):
    consistent = "consistent"
    inconsistent = "inconsistent"
    unknown = "unknown"
    not_applicable = "not_applicable"
    not_evaluated = "not_evaluated"
    blocked = "blocked"


class RuleSeverity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"


class RuleRunStatus(str, Enum):
    consistent = "consistent"
    inconsistent = "inconsistent"
    incomplete = "incomplete"
    not_applicable = "not_applicable"
    blocked = "blocked"


class RuleApplicability(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    case_types: list[str] = Field(default_factory=list)
    inspection_profiles: list[str] = Field(default_factory=list)
    required_backends: list[str] = Field(default_factory=list)
    physics_tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RuleEvidenceRequirement(BaseModel):
    path: str
    description: str
    required: bool = True

    @field_validator("path")
    @classmethod
    def json_pointer_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("evidence requirement paths must be absolute JSON pointers")
        return value


class RuleEvidenceRef(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    path: str
    source_path: str | None = None
    value: Any = None
    evidence_state: str = "explicit"
    note: str | None = None

    @field_validator("path")
    @classmethod
    def json_pointer_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("evidence paths must be absolute JSON pointers")
        return value

    @field_validator("value")
    @classmethod
    def compact_value(cls, value: Any) -> Any:
        _validate_compact(value)
        return value


class PhysicsRuleDefinition(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    rule_id: str
    rule_version: str
    pack_id: str
    pack_version: str
    title: str
    category: str
    description: str
    severity: RuleSeverity = RuleSeverity.warning
    applicability: RuleApplicability = Field(default_factory=RuleApplicability)
    required_evidence: list[RuleEvidenceRequirement] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    remediation: str
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def stable_identity(self) -> "PhysicsRuleDefinition":
        for label, value in (
            ("rule_id", self.rule_id),
            ("rule_version", self.rule_version),
            ("pack_id", self.pack_id),
            ("pack_version", self.pack_version),
        ):
            if not value or value.strip() != value:
                raise ValueError(f"{label} must be a non-empty stable identifier")
        return self


class PhysicsRuleEvaluation(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    rule_id: str
    rule_version: str
    pack_id: str
    pack_version: str
    status: RuleEvaluationStatus
    severity: RuleSeverity
    message: str
    evidence: list[RuleEvidenceRef] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    assumptions_applied: list[str] = Field(default_factory=list)
    remediation: str
    limitations: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def compact_details(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_compact(value)
        return value


class PhysicsRulePackManifest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    protocol_version: str = RULE_PROTOCOL_VERSION
    pack_id: str
    pack_version: str
    title: str
    domain: str
    description: str
    rule_ids: list[str]
    scope: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("rule_ids")
    @classmethod
    def unique_ordered_rules(cls, value: list[str]) -> list[str]:
        if not value or len(set(value)) != len(value):
            raise ValueError("rule_ids must be non-empty and unique")
        return value


class PhysicsRuleRunReport(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    protocol_version: str = RULE_PROTOCOL_VERSION
    pack_id: str
    pack_version: str
    case_id: str
    run_id: str
    input_sha256: str
    canonical_sha256: str | None = None
    status: RuleRunStatus
    results: list[PhysicsRuleEvaluation]
    counts: dict[str, int]
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ordered_unique_results(self) -> "PhysicsRuleRunReport":
        ids = [item.rule_id for item in self.results]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("rule results must be uniquely and deterministically ordered")
        return self


@runtime_checkable
class PhysicsRule(Protocol):
    definition: PhysicsRuleDefinition

    def evaluate(self, context: Any) -> PhysicsRuleEvaluation:
        ...


class PhysicsRulePack(BaseModel):
    """Serializable pack wrapper used for discovery and documentation."""

    manifest: PhysicsRulePackManifest


class RuleEvaluationError(RuntimeError):
    """Base error for deterministic rule evaluation."""


class RuleBlockedError(RuleEvaluationError):
    """Raised when required evidence exists but cannot be trusted or accessed."""


class RulePackNotFoundError(RuleEvaluationError):
    """Raised when a requested pack is not registered."""


def _validate_compact(value: Any, *, depth: int = 0) -> None:
    if depth > 8:
        raise ValueError("compact rule evidence exceeds maximum nesting depth")
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        import math

        if not math.isfinite(value):
            raise ValueError("compact rule evidence cannot contain non-finite numbers")
        return
    if isinstance(value, bytes):
        raise ValueError("binary payloads are not allowed in rule evidence")
    if isinstance(value, (list, tuple)):
        if len(value) > 64:
            raise ValueError("large sequences must remain behind ArrayRef handles")
        for item in value:
            _validate_compact(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 64:
            raise ValueError("compact rule evidence contains too many keys")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("compact rule evidence keys must be strings")
            _validate_compact(item, depth=depth + 1)
        return
    raise ValueError(f"unsupported compact rule evidence type: {type(value).__name__}")


__all__ = [
    "RULE_PROTOCOL_VERSION",
    "PhysicsRule",
    "PhysicsRuleDefinition",
    "PhysicsRuleEvaluation",
    "PhysicsRulePack",
    "PhysicsRulePackManifest",
    "PhysicsRuleRunReport",
    "RuleApplicability",
    "RuleBlockedError",
    "RuleEvaluationError",
    "RuleEvaluationStatus",
    "RuleEvidenceRef",
    "RuleEvidenceRequirement",
    "RulePackNotFoundError",
    "RuleRunStatus",
    "RuleSeverity",
]
