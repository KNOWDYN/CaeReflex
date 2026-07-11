"""OpenFOAM mesh-topology consistency rule."""
from __future__ import annotations

from typing import Any

from caereflex.rules.context import RuleEvaluationContext
from caereflex.rules.contracts import PhysicsRuleEvaluation, RuleEvaluationStatus, RuleSeverity
from caereflex.rules.openfoam_common import _definition, _evaluation, _int


class OpenFOAMMeshTopologyRule:
    definition = _definition(
        "OF-CFD-MESH-001",
        title="OpenFOAM mesh topology cardinality",
        category="mesh_topology",
        description="Checks native mesh counts and content-addressed topology-array cardinalities and label ranges.",
        remediation="Re-export or repair polyMesh so points, faces, owner, neighbour and boundary agree, then rerun deep inspection.",
        deep=True,
        severity=RuleSeverity.error,
        required=[
            ("/metadata/native_openfoam/mesh", "Native OpenFOAM mesh summary"),
            ("/array_references", "Registered content-addressed topology arrays"),
        ],
    )

    def evaluate(self, context: RuleEvaluationContext) -> PhysicsRuleEvaluation:
        native = context.native_openfoam
        if native is None:
            return _evaluation(self.definition, RuleEvaluationStatus.unknown, "Native OpenFOAM mesh evidence is absent.", missing=["/metadata/native_openfoam"])
        mesh = native.get("mesh")
        if not isinstance(mesh, dict):
            return _evaluation(self.definition, RuleEvaluationStatus.unknown, "Native OpenFOAM mesh summary is unavailable.", missing=["/metadata/native_openfoam/mesh"])
        keys = ("points", "faces", "cells", "internal_faces", "complete_topology")
        missing = [f"/metadata/native_openfoam/mesh/{key}" for key in keys if key not in mesh]
        if missing:
            return _evaluation(self.definition, RuleEvaluationStatus.unknown, "Mesh cardinality evidence is incomplete.", missing=missing)

        points = _int(mesh.get("points"))
        faces = _int(mesh.get("faces"))
        cells = _int(mesh.get("cells"))
        internal = _int(mesh.get("internal_faces"))
        evidence = [context.evidence(f"/metadata/native_openfoam/mesh/{key}") for key in keys]
        if not all(value is not None for value in (points, faces, cells, internal)):
            return _evaluation(self.definition, RuleEvaluationStatus.inconsistent, "One or more mesh counts are not integers.", evidence=evidence)
        assert points is not None and faces is not None and cells is not None and internal is not None
        violations: list[str] = []
        if points <= 0:
            violations.append("points must be positive")
        if faces <= 0:
            violations.append("faces must be positive")
        if cells <= 0:
            violations.append("cells must be positive")
        if internal < 0 or internal > faces:
            violations.append("internal_faces must lie between zero and faces")
        if mesh.get("complete_topology") is not True:
            return _evaluation(
                self.definition,
                RuleEvaluationStatus.unknown,
                "The native reader did not establish a complete topology inventory.",
                evidence=evidence,
                missing=["complete decoded points/faces/owner/neighbour/boundary evidence"],
            )

        specs = {
            "points_array_id": ((points, 3), "point coordinates"),
            "face_offsets_array_id": ((faces + 1,), "face offsets"),
            "owner_array_id": ((faces,), "owner labels"),
            "neighbour_array_id": ((internal,), "neighbour labels"),
        }
        refs: dict[str, Any] = {}
        for key, (shape, label) in specs.items():
            pointer = f"/metadata/native_openfoam/mesh/{key}"
            array_id = mesh.get(key)
            evidence.append(context.evidence(pointer))
            ref = context.require_array_ref(array_id, evidence_path=pointer)
            refs[key] = ref
            if tuple(ref.shape) != shape:
                violations.append(f"{label} shape {tuple(ref.shape)} does not match expected {shape}")

        connectivity_id = mesh.get("face_connectivity_array_id")
        pointer = "/metadata/native_openfoam/mesh/face_connectivity_array_id"
        evidence.append(context.evidence(pointer))
        connectivity = context.require_array_ref(connectivity_id, evidence_path=pointer)
        refs["face_connectivity_array_id"] = connectivity
        if len(connectivity.shape) != 1:
            violations.append("face connectivity must be a flat one-dimensional array")

        if violations:
            return _evaluation(self.definition, RuleEvaluationStatus.inconsistent, "OpenFOAM topology cardinalities conflict.", evidence=evidence, details={"violations": violations})

        owner_min = context.array_reduce(str(mesh["owner_array_id"]), "min")["value"]
        owner_max = context.array_reduce(str(mesh["owner_array_id"]), "max")["value"]
        neighbour_min = context.array_reduce(str(mesh["neighbour_array_id"]), "min")["value"] if internal else None
        neighbour_max = context.array_reduce(str(mesh["neighbour_array_id"]), "max")["value"] if internal else None
        conn_min = context.array_reduce(str(connectivity_id), "min")["value"]
        conn_max = context.array_reduce(str(connectivity_id), "max")["value"]
        offsets_id = str(mesh["face_offsets_array_id"])
        offsets_min = context.array_reduce(offsets_id, "min")["value"]
        offsets_max = context.array_reduce(offsets_id, "max")["value"]
        first_offset = context.array_slice(offsets_id, 0, 1)["values"][0]
        last_offset = context.array_slice(offsets_id, faces, faces + 1)["values"][0]
        connectivity_count = int(connectivity.shape[0])

        if owner_min is None or owner_min < 0 or owner_max is None or owner_max >= cells:
            violations.append("owner labels fall outside the declared cell range")
        if internal and (neighbour_min is None or neighbour_min < 0 or neighbour_max is None or neighbour_max >= cells):
            violations.append("neighbour labels fall outside the declared cell range")
        if conn_min is None or conn_min < 0 or conn_max is None or conn_max >= points:
            violations.append("face connectivity references points outside the declared point range")
        if first_offset != 0 or last_offset != connectivity_count or offsets_min != 0 or offsets_max != connectivity_count:
            violations.append("face offsets do not span the complete connectivity array")

        evidence.extend([
            context.array_query_evidence(str(mesh["owner_array_id"]), operation="min", value=owner_min),
            context.array_query_evidence(str(mesh["owner_array_id"]), operation="max", value=owner_max),
            context.array_query_evidence(str(connectivity_id), operation="min", value=conn_min),
            context.array_query_evidence(str(connectivity_id), operation="max", value=conn_max),
            context.array_query_evidence(offsets_id, operation="slice:first", value=first_offset),
            context.array_query_evidence(offsets_id, operation="slice:last", value=last_offset),
        ])
        if internal:
            evidence.extend([
                context.array_query_evidence(str(mesh["neighbour_array_id"]), operation="min", value=neighbour_min),
                context.array_query_evidence(str(mesh["neighbour_array_id"]), operation="max", value=neighbour_max),
            ])
        if violations:
            return _evaluation(self.definition, RuleEvaluationStatus.inconsistent, "OpenFOAM topology labels or offsets conflict with declared counts.", evidence=evidence, details={"violations": violations})
        return _evaluation(self.definition, RuleEvaluationStatus.consistent, "Decoded OpenFOAM topology counts, array shapes and bounded label ranges are mutually consistent.", evidence=evidence)


__all__ = ["OpenFOAMMeshTopologyRule"]
