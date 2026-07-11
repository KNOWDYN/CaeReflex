"""First versioned OpenFOAM CFD evidence-consistency rule pack.

The rules inspect declared dimensions, field classes and native topology summaries.
They do not judge turbulence-model choice, convergence, mesh independence,
experimental validity, numerical accuracy, or engineering safety.
"""
from __future__ import annotations

from typing import Any

from caereflex.physics.contracts import (
    EvidencePointer,
    RuleDefinition,
    RulePackManifest,
    RuleResult,
    RuleSeverity,
    RuleStatus,
)
from caereflex.physics.engine import PhysicsRuleEngine, RegisteredRule

OPENFOAM_CFD_RULE_PACK_VERSION = "1.0.0"
OPENFOAM_CFD_RULE_PACK_ID = "caereflex.openfoam-cfd"

VELOCITY = [0, 1, -1, 0, 0, 0, 0]
KINEMATIC_PRESSURE = [0, 2, -2, 0, 0, 0, 0]
THERMODYNAMIC_PRESSURE = [1, -1, -2, 0, 0, 0, 0]
KINEMATIC_VISCOSITY = [0, 2, -1, 0, 0, 0, 0]

LIMITATION = (
    "This result checks internal consistency of available declarations only. It does not prove "
    "physical validity, numerical convergence, mesh adequacy, turbulence-model suitability, "
    "experimental agreement, certification, or design safety."
)


def _pointer(path: str, description: str, value: Any = None, source_path: str | None = None) -> EvidencePointer:
    return EvidencePointer(path=path, description=description, value=value, source_path=source_path)


def _fields(context: dict[str, Any]) -> list[dict[str, Any]]:
    fields = context.get("fields", [])
    return [item for item in fields if isinstance(item, dict)] if isinstance(fields, list) else []


def _field(context: dict[str, Any], name: str) -> tuple[int, dict[str, Any]] | None:
    for index, item in enumerate(_fields(context)):
        if str(item.get("name") or item.get("object") or "") == name:
            return index, item
    return None


def _dimensions(item: dict[str, Any]) -> list[int] | None:
    value = item.get("dimensions")
    if isinstance(value, dict):
        value = value.get("exponents") or value.get("vector")
    if isinstance(value, (list, tuple)) and len(value) == 7:
        try:
            return [int(entry) for entry in value]
        except (TypeError, ValueError):
            return None
    return None


def _dimension_rule(name: str, accepted: list[list[int]], title: str, remediation: str):
    def evaluate(context: dict[str, Any], definition: RuleDefinition) -> RuleResult:
        found = _field(context, name)
        if found is None:
            return RuleResult(rule_id=definition.rule_id, rule_version=definition.version,
                status=RuleStatus.unknown, severity=RuleSeverity.warning,
                message=f"Field {name!r} was not available in the inspected evidence.",
                missing_evidence=[f"field:{name}", f"field:{name}:dimensions"], assumptions=definition.assumptions,
                remediation=f"Provide a parseable OpenFOAM {name} field with an explicit dimensions declaration.", limitation=definition.limitation)
        index, item = found
        dimensions = _dimensions(item)
        source = item.get("source_path")
        if dimensions is None:
            return RuleResult(rule_id=definition.rule_id, rule_version=definition.version,
                status=RuleStatus.blocked, severity=RuleSeverity.warning,
                message=f"Field {name!r} exists, but its seven-component dimensions are unavailable or malformed.",
                evidence=[_pointer(f"/fields/{index}", f"OpenFOAM field {name}", source_path=source)],
                missing_evidence=[f"field:{name}:dimensions"], assumptions=definition.assumptions,
                remediation="Restore or supply the explicit OpenFOAM dimensions declaration; do not infer it from the field name.", limitation=definition.limitation)
        status = RuleStatus.consistent if dimensions in accepted else RuleStatus.inconsistent
        severity = RuleSeverity.information if status == RuleStatus.consistent else RuleSeverity.error
        message = f"Field {name!r} dimensions are consistent with {title}." if status == RuleStatus.consistent else f"Field {name!r} dimensions conflict with {title}."
        return RuleResult(rule_id=definition.rule_id, rule_version=definition.version,
            status=status, severity=severity, message=message,
            evidence=[_pointer(f"/fields/{index}/dimensions", f"Declared dimensions for {name}", dimensions, source)],
            assumptions=definition.assumptions, remediation=None if status == RuleStatus.consistent else remediation,
            limitation=definition.limitation)
    return evaluate


def _topology_counts(context: dict[str, Any], definition: RuleDefinition) -> RuleResult:
    mesh = context.get("mesh")
    if not isinstance(mesh, dict):
        return RuleResult(rule_id=definition.rule_id, rule_version=definition.version,
            status=RuleStatus.not_evaluated, severity=RuleSeverity.information,
            message="No native OpenFOAM mesh summary was available.", missing_evidence=["mesh-summary"],
            assumptions=definition.assumptions, remediation="Run deep native OpenFOAM inspection.", limitation=definition.limitation)
    required = ["face_count", "internal_face_count", "boundary_face_count", "cell_count"]
    if any(not isinstance(mesh.get(key), int) for key in required):
        return RuleResult(rule_id=definition.rule_id, rule_version=definition.version,
            status=RuleStatus.blocked, severity=RuleSeverity.warning,
            message="OpenFOAM topology counts were incomplete.", missing_evidence=[key for key in required if not isinstance(mesh.get(key), int)],
            assumptions=definition.assumptions, remediation="Provide a complete decoded polyMesh summary.", limitation=definition.limitation)
    faces = mesh["face_count"]
    internal = mesh["internal_face_count"]
    boundary = mesh["boundary_face_count"]
    cells = mesh["cell_count"]
    valid = faces >= 0 and cells >= 0 and 0 <= internal <= faces and boundary == faces - internal
    return RuleResult(rule_id=definition.rule_id, rule_version=definition.version,
        status=RuleStatus.consistent if valid else RuleStatus.inconsistent,
        severity=RuleSeverity.information if valid else RuleSeverity.error,
        message="OpenFOAM face accounting is internally consistent." if valid else "OpenFOAM face accounting is internally inconsistent.",
        evidence=[_pointer("/mesh/face_count", "Total faces", faces), _pointer("/mesh/internal_face_count", "Internal faces", internal), _pointer("/mesh/boundary_face_count", "Boundary faces", boundary), _pointer("/mesh/cell_count", "Cells", cells)],
        assumptions=definition.assumptions, remediation=None if valid else "Re-read points/faces/owner/neighbour/boundary and resolve count mismatches before downstream use.", limitation=definition.limitation)


def _patch_ranges(context: dict[str, Any], definition: RuleDefinition) -> RuleResult:
    mesh = context.get("mesh")
    patches = context.get("patches")
    if not isinstance(mesh, dict) or not isinstance(patches, list):
        return RuleResult(rule_id=definition.rule_id, rule_version=definition.version,
            status=RuleStatus.not_evaluated, severity=RuleSeverity.information,
            message="Boundary patch range evidence was unavailable.", missing_evidence=["mesh:face_count", "patches"],
            assumptions=definition.assumptions, remediation="Run native OpenFOAM boundary inspection.", limitation=definition.limitation)
    face_count = mesh.get("face_count")
    internal = mesh.get("internal_face_count")
    if not isinstance(face_count, int) or not isinstance(internal, int):
        return RuleResult(rule_id=definition.rule_id, rule_version=definition.version,
            status=RuleStatus.blocked, severity=RuleSeverity.warning, message="Patch ranges cannot be checked without face counts.",
            missing_evidence=["mesh:face_count", "mesh:internal_face_count"], assumptions=definition.assumptions,
            remediation="Supply complete mesh counts.", limitation=definition.limitation)
    ranges: list[tuple[int, int, int]] = []
    evidence: list[EvidencePointer] = []
    for index, patch in enumerate(patches):
        if not isinstance(patch, dict) or not isinstance(patch.get("start_face"), int) or not isinstance(patch.get("face_count"), int):
            return RuleResult(rule_id=definition.rule_id, rule_version=definition.version,
                status=RuleStatus.blocked, severity=RuleSeverity.warning, message="At least one patch range is incomplete.",
                evidence=evidence, missing_evidence=[f"patches[{index}]:start_face/face_count"], assumptions=definition.assumptions,
                remediation="Restore the complete boundary entry.", limitation=definition.limitation)
        start, count = patch["start_face"], patch["face_count"]
        ranges.append((start, start + count, index))
        evidence.append(_pointer(f"/patches/{index}", "Boundary patch range", {"start_face": start, "face_count": count}, patch.get("source_path")))
    ranges.sort()
    valid = all(start >= internal and end <= face_count and start <= end for start, end, _ in ranges)
    valid = valid and all(ranges[i][1] <= ranges[i + 1][0] for i in range(len(ranges) - 1))
    covered = sum(end - start for start, end, _ in ranges)
    valid = valid and covered == face_count - internal
    return RuleResult(rule_id=definition.rule_id, rule_version=definition.version,
        status=RuleStatus.consistent if valid else RuleStatus.inconsistent,
        severity=RuleSeverity.information if valid else RuleSeverity.error,
        message="Boundary patch ranges are non-overlapping and cover all boundary faces." if valid else "Boundary patch ranges overlap, escape the boundary interval, or do not cover all boundary faces.",
        evidence=evidence, assumptions=definition.assumptions,
        remediation=None if valid else "Correct the OpenFOAM boundary startFace/nFaces declarations or regenerate a consistent boundary file.", limitation=definition.limitation)


def _field_class_association(context: dict[str, Any], definition: RuleDefinition) -> RuleResult:
    fields = _fields(context)
    if not fields:
        return RuleResult(rule_id=definition.rule_id, rule_version=definition.version,
            status=RuleStatus.unknown, severity=RuleSeverity.information, message="No decoded OpenFOAM fields were available.",
            missing_evidence=["fields"], assumptions=definition.assumptions, remediation="Provide decoded field headers.", limitation=definition.limitation)
    inconsistent: list[EvidencePointer] = []
    inspected: list[EvidencePointer] = []
    for index, item in enumerate(fields):
        field_class = str(item.get("class") or item.get("field_class") or "")
        association = str(item.get("association") or "")
        inspected.append(_pointer(f"/fields/{index}", "Field class and association", {"class": field_class, "association": association}, item.get("source_path")))
        expected = "cell" if field_class.startswith("vol") else "face" if field_class.startswith("surface") else "point" if field_class.startswith("point") else None
        if expected is not None and association and association not in {expected, expected + "s"}:
            inconsistent.append(inspected[-1])
    return RuleResult(rule_id=definition.rule_id, rule_version=definition.version,
        status=RuleStatus.inconsistent if inconsistent else RuleStatus.consistent,
        severity=RuleSeverity.error if inconsistent else RuleSeverity.information,
        message=f"{len(inconsistent)} field class/association conflict(s) found." if inconsistent else "Decoded field classes agree with their declared associations.",
        evidence=inconsistent or inspected, assumptions=definition.assumptions,
        remediation="Correct field ownership metadata or parser mapping before spatial or physics use." if inconsistent else None,
        limitation=definition.limitation)


DEFINITIONS = [
    RuleDefinition(rule_id="OF-CFD-DIM-U-001", version="1.0.0", title="Velocity dimensions", description="Checks U against velocity dimensions.", domain="OpenFOAM CFD", applicability="A field named U is expected in the inspected case.", required_evidence=["U dimensions"], assumptions=["The object named U represents velocity."], limitation=LIMITATION, default_severity=RuleSeverity.error),
    RuleDefinition(rule_id="OF-CFD-DIM-P-001", version="1.0.0", title="Pressure dimensions", description="Accepts thermodynamic or incompressible kinematic pressure dimensions for p.", domain="OpenFOAM CFD", applicability="A field named p is expected in the inspected case.", required_evidence=["p dimensions"], assumptions=["The object named p represents pressure under the solver convention."], limitation=LIMITATION, default_severity=RuleSeverity.error),
    RuleDefinition(rule_id="OF-CFD-DIM-NU-001", version="1.0.0", title="Kinematic viscosity dimensions", description="Checks nu against kinematic-viscosity dimensions.", domain="OpenFOAM CFD", applicability="A field or property named nu is available.", required_evidence=["nu dimensions"], assumptions=["The object named nu represents kinematic viscosity."], limitation=LIMITATION, default_severity=RuleSeverity.error),
    RuleDefinition(rule_id="OF-CFD-TOPO-COUNT-001", version="1.0.0", title="Mesh topology accounting", description="Checks face, internal-face and boundary-face accounting.", domain="OpenFOAM CFD", applicability="A decoded polyMesh summary is available.", required_evidence=["face counts", "cell count"], assumptions=[], limitation=LIMITATION),
    RuleDefinition(rule_id="OF-CFD-PATCH-RANGE-001", version="1.0.0", title="Boundary patch ranges", description="Checks patch ranges for coverage and overlap.", domain="OpenFOAM CFD", applicability="Decoded boundary ranges are available.", required_evidence=["patch startFace", "patch nFaces"], assumptions=["The native summary preserves OpenFOAM boundary indexing."], limitation=LIMITATION),
    RuleDefinition(rule_id="OF-CFD-FIELD-ASSOC-001", version="1.0.0", title="Field class association", description="Checks vol/surface/point field classes against mapped association.", domain="OpenFOAM CFD", applicability="Decoded field headers are available.", required_evidence=["field class", "field association"], assumptions=[], limitation=LIMITATION),
]

MANIFEST = RulePackManifest(
    pack_id=OPENFOAM_CFD_RULE_PACK_ID,
    version=OPENFOAM_CFD_RULE_PACK_VERSION,
    title="CaeReflex OpenFOAM CFD consistency rules",
    backend="openfoam.native",
    rule_ids=sorted(item.rule_id for item in DEFINITIONS),
    exclusions=["convergence", "mesh independence", "turbulence-model suitability", "experimental validation", "numerical accuracy", "certification", "design safety"],
)


def openfoam_cfd_engine() -> PhysicsRuleEngine:
    by_id = {item.rule_id: item for item in DEFINITIONS}
    evaluators = {
        "OF-CFD-DIM-U-001": _dimension_rule("U", [VELOCITY], "velocity", "Correct the U dimensions or field identity."),
        "OF-CFD-DIM-P-001": _dimension_rule("p", [KINEMATIC_PRESSURE, THERMODYNAMIC_PRESSURE], "an accepted OpenFOAM pressure convention", "Resolve the solver pressure convention and correct p dimensions."),
        "OF-CFD-DIM-NU-001": _dimension_rule("nu", [KINEMATIC_VISCOSITY], "kinematic viscosity", "Correct the nu dimensions or property identity."),
        "OF-CFD-TOPO-COUNT-001": _topology_counts,
        "OF-CFD-PATCH-RANGE-001": _patch_ranges,
        "OF-CFD-FIELD-ASSOC-001": _field_class_association,
    }
    return PhysicsRuleEngine(MANIFEST, [RegisteredRule(by_id[key], evaluators[key]) for key in sorted(evaluators)])


def evaluate_openfoam_cfd(context: dict[str, Any], *, case_id: str | None = None):
    return openfoam_cfd_engine().evaluate(context, case_id=case_id, backend_id="openfoam.native")
