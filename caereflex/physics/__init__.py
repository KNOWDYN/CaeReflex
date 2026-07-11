"""Deterministic physics-consistency rules."""
from caereflex.physics.context import openfoam_rule_context
from caereflex.physics.contracts import (
    PHYSICS_RULE_PROTOCOL_VERSION,
    EvidencePointer,
    RuleDefinition,
    RuleEvaluationReport,
    RulePackManifest,
    RuleResult,
    RuleSeverity,
    RuleStatus,
)
from caereflex.physics.engine import PhysicsRuleEngine, RegisteredRule
from caereflex.physics.openfoam import (
    OPENFOAM_CFD_RULE_PACK_ID,
    OPENFOAM_CFD_RULE_PACK_VERSION,
    evaluate_openfoam_cfd,
    openfoam_cfd_engine,
)

__all__ = [
    "PHYSICS_RULE_PROTOCOL_VERSION",
    "OPENFOAM_CFD_RULE_PACK_ID",
    "OPENFOAM_CFD_RULE_PACK_VERSION",
    "EvidencePointer",
    "RuleDefinition",
    "RuleEvaluationReport",
    "RulePackManifest",
    "RuleResult",
    "RuleSeverity",
    "RuleStatus",
    "PhysicsRuleEngine",
    "RegisteredRule",
    "openfoam_rule_context",
    "openfoam_cfd_engine",
    "evaluate_openfoam_cfd",
]
