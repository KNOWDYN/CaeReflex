"""OpenFOAM CFD consistency rule pack v1.0.0."""
from caereflex.rules.contracts import PhysicsRulePackManifest
from caereflex.rules.engine import RegisteredRulePack, register_rule_pack
from caereflex.rules.openfoam_common import (
    OPENFOAM_CFD_PACK_ID,
    OPENFOAM_CFD_PACK_VERSION,
    _COMMON_LIMITATIONS,
)
from caereflex.rules.openfoam_boundary import (
    OpenFOAMBoundaryPartitionRule,
    OpenFOAMBoundaryReferenceRule,
)
from caereflex.rules.openfoam_fields import (
    OpenFOAMDimensionalSemanticsRule,
    OpenFOAMFieldCardinalityRule,
)
from caereflex.rules.openfoam_mesh import OpenFOAMMeshTopologyRule
from caereflex.rules.openfoam_time import OpenFOAMTimeControlsRule

_RULES = [
    OpenFOAMBoundaryPartitionRule(),
    OpenFOAMBoundaryReferenceRule(),
    OpenFOAMDimensionalSemanticsRule(),
    OpenFOAMFieldCardinalityRule(),
    OpenFOAMMeshTopologyRule(),
    OpenFOAMTimeControlsRule(),
]

OPENFOAM_CFD_PACK_MANIFEST = PhysicsRulePackManifest(
    pack_id=OPENFOAM_CFD_PACK_ID,
    pack_version=OPENFOAM_CFD_PACK_VERSION,
    title="OpenFOAM CFD core consistency rules",
    domain="OpenFOAM finite-volume CFD",
    description="Deterministic evidence checks for topology, patch partitioning, field association, declared dimensions, patch references and time controls.",
    rule_ids=sorted(rule.definition.rule_id for rule in _RULES),
    scope=[
        "Decoded OpenFOAM polyMesh cardinality and bounded label ranges",
        "Boundary patch range partitioning",
        "Internal-field tuple cardinality and ArrayRef shape",
        "Gate 4 dimensional conflict states",
        "Parsed boundary patch references",
        "Declared controlDict time ordering",
    ],
    limitations=list(_COMMON_LIMITATIONS),
)

OPENFOAM_CFD_RULE_PACK = register_rule_pack(
    RegisteredRulePack(OPENFOAM_CFD_PACK_MANIFEST, _RULES),
    replace=True,
)

__all__ = [
    "OPENFOAM_CFD_PACK_ID",
    "OPENFOAM_CFD_PACK_MANIFEST",
    "OPENFOAM_CFD_PACK_VERSION",
    "OPENFOAM_CFD_RULE_PACK",
]
