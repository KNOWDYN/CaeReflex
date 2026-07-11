"""OpenFOAM boundary partition and reference consistency rules."""
from __future__ import annotations

from collections import defaultdict

from caereflex.rules.context import RuleEvaluationContext
from caereflex.rules.contracts import PhysicsRuleEvaluation, RuleEvaluationStatus, RuleSeverity
from caereflex.rules.openfoam_common import _COMMON_LIMITATIONS, _definition, _evaluation, _int


class OpenFOAMBoundaryPartitionRule:
    definition = _definition(
        "OF-CFD-BOUNDARY-001",
        title="OpenFOAM boundary-face partition",
        category="boundary_topology",
        description="Checks that explicit patch ranges form a unique, contiguous partition of boundary faces.",
        remediation="Correct nFaces/startFace entries and patch duplication in constant/polyMesh/boundary.",
        deep=True,
        severity=RuleSeverity.error,
        required=[
            ("/metadata/native_openfoam/mesh/faces", "Total face count"),
            ("/metadata/native_openfoam/mesh/internal_faces", "Internal face count"),
            ("/metadata/native_openfoam/patches", "Decoded boundary patch ranges"),
        ],
    )

    def evaluate(self, context: RuleEvaluationContext) -> PhysicsRuleEvaluation:
        native = context.native_openfoam or {}
        mesh = native.get("mesh") if isinstance(native.get("mesh"), dict) else {}
        patches = native.get("patches")
        faces = _int(mesh.get("faces"))
        internal = _int(mesh.get("internal_faces"))
        missing: list[str] = []
        if faces is None:
            missing.append("/metadata/native_openfoam/mesh/faces")
        if internal is None:
            missing.append("/metadata/native_openfoam/mesh/internal_faces")
        if not isinstance(patches, list):
            missing.append("/metadata/native_openfoam/patches")
        if missing:
            return _evaluation(self.definition, RuleEvaluationStatus.unknown, "Boundary partition evidence is incomplete.", missing=missing)
        assert faces is not None and internal is not None and isinstance(patches, list)
        evidence = [
            context.evidence("/metadata/native_openfoam/mesh/faces"),
            context.evidence("/metadata/native_openfoam/mesh/internal_faces"),
            context.evidence("/metadata/native_openfoam/patches"),
        ]
        boundary_faces = faces - internal
        if boundary_faces < 0:
            return _evaluation(self.definition, RuleEvaluationStatus.inconsistent, "Internal face count exceeds total face count.", evidence=evidence)
        if not patches:
            status = RuleEvaluationStatus.consistent if boundary_faces == 0 else RuleEvaluationStatus.unknown
            message = "No boundary patches are required by the declared face counts." if boundary_faces == 0 else "Boundary faces exist but no complete patch inventory was decoded."
            return _evaluation(self.definition, status, message, evidence=evidence)

        ranges: list[tuple[int, int, str]] = []
        names: set[str] = set()
        violations: list[str] = []
        for index, patch in enumerate(patches):
            if not isinstance(patch, dict):
                violations.append(f"patch {index} is not an object")
                continue
            name = str(patch.get("name") or "")
            start = _int(patch.get("start_face"))
            count = _int(patch.get("n_faces"))
            if not name:
                violations.append(f"patch {index} has no name")
            elif name in names:
                violations.append(f"duplicate patch name {name!r}")
            names.add(name)
            if start is None or count is None:
                return _evaluation(
                    self.definition,
                    RuleEvaluationStatus.unknown,
                    "At least one patch lacks an explicit integer startFace or nFaces.",
                    evidence=evidence,
                    missing=[
                        f"/metadata/native_openfoam/patches/{index}/start_face",
                        f"/metadata/native_openfoam/patches/{index}/n_faces",
                    ],
                )
            if count < 0 or start < internal or start + count > faces:
                violations.append(f"patch {name!r} range [{start}, {start + count}) is outside boundary face range [{internal}, {faces})")
            ranges.append((start, start + count, name))
        ranges.sort()
        cursor = internal
        for start, end, name in ranges:
            if start != cursor:
                violations.append(f"patch {name!r} starts at {start}, expected contiguous start {cursor}")
            cursor = max(cursor, end)
        if cursor != faces:
            violations.append(f"patch ranges end at {cursor}, expected {faces}")
        if violations:
            return _evaluation(self.definition, RuleEvaluationStatus.inconsistent, "OpenFOAM patch ranges do not form a valid boundary partition.", evidence=evidence, details={"violations": violations})
        return _evaluation(self.definition, RuleEvaluationStatus.consistent, "Patch ranges uniquely and contiguously partition all declared boundary faces.", evidence=evidence, details={"boundary_face_count": boundary_faces, "patch_count": len(patches)})


class OpenFOAMBoundaryReferenceRule:
    definition = _definition(
        "OF-CFD-BC-001",
        title="OpenFOAM boundary-condition patch references",
        category="boundary_conditions",
        description="Checks that parsed mesh and field boundary records reference native patch names without contradictory patch types.",
        remediation="Align boundaryField patch names and mesh patch declarations; manually review any parser-incomplete field dictionaries.",
        deep=True,
        required=[
            ("/metadata/native_openfoam/patches", "Native mesh patch names and types"),
            ("/boundary_conditions", "Parsed mesh and field boundary records"),
        ],
        limitations=list(_COMMON_LIMITATIONS) + ["A structurally aligned boundary condition can still be physically unsuitable."],
    )

    def evaluate(self, context: RuleEvaluationContext) -> PhysicsRuleEvaluation:
        native = context.native_openfoam or {}
        patches = native.get("patches")
        if not isinstance(patches, list) or not patches:
            return _evaluation(self.definition, RuleEvaluationStatus.unknown, "No complete native patch inventory is available.", missing=["/metadata/native_openfoam/patches"])
        patch_types = {
            str(item.get("name")): item.get("type")
            for item in patches
            if isinstance(item, dict) and item.get("name")
        }
        records = [item.model_dump(mode="json") for item in context.case.boundary_conditions]
        if not records:
            return _evaluation(self.definition, RuleEvaluationStatus.unknown, "No parsed boundary-condition records are available.", missing=["/boundary_conditions"])
        evidence = [context.evidence("/metadata/native_openfoam/patches"), context.evidence("/boundary_conditions")]
        violations: list[str] = []
        field_coverage: dict[str, set[str]] = defaultdict(set)
        for index, record in enumerate(records):
            patch = str(record.get("patch") or "")
            field = record.get("field")
            boundary_type = record.get("type")
            if patch not in patch_types:
                violations.append(f"boundary record {index} references unknown patch {patch!r}")
                continue
            if field:
                field_coverage[str(field)].add(patch)
            elif boundary_type and patch_types.get(patch) and str(boundary_type) != str(patch_types[patch]):
                violations.append(f"mesh patch {patch!r} type {boundary_type!r} conflicts with native type {patch_types[patch]!r}")
        if violations:
            return _evaluation(self.definition, RuleEvaluationStatus.inconsistent, "Parsed boundary records contradict the native mesh patch inventory.", evidence=evidence, details={"violations": violations})
        missing_coverage = {
            field: sorted(set(patch_types) - covered)
            for field, covered in sorted(field_coverage.items())
            if set(patch_types) - covered
        }
        if missing_coverage:
            return _evaluation(
                self.definition,
                RuleEvaluationStatus.unknown,
                "Recorded patch references are valid, but complete boundaryField coverage was not established by the bounded parser.",
                evidence=evidence,
                details={"missing_parsed_coverage": missing_coverage},
            )
        return _evaluation(self.definition, RuleEvaluationStatus.consistent, "All parsed boundary records reference known native patches without contradictory mesh patch types.", evidence=evidence, details={"patch_count": len(patch_types), "field_count": len(field_coverage)})


__all__ = ["OpenFOAMBoundaryPartitionRule", "OpenFOAMBoundaryReferenceRule"]
