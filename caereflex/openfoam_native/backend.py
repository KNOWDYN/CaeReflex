"""Isolated first-party OpenFOAM native inspection backend."""
from __future__ import annotations

from dataclasses import asdict
import time
import uuid
from pathlib import PurePosixPath
from typing import Any

from caereflex.contracts import (
    AttemptOutcome,
    DiagnosticEvent,
    DiagnosticSeverity,
    InspectionExecutionRequest,
    ParserAttempt,
)
from caereflex.core.provenance import utc_now_iso
from caereflex.execution.context import ExecutionContext, ExecutionContextError
from caereflex.units import OpenFOAMQuantityError, build_openfoam_quantity_evidence, parse_openfoam_dimensioned_value

from .parser import (
    DecodedFoamText,
    OpenFOAMNativeError,
    OpenFOAMUnsupportedError,
    build_mesh,
    canonical_openfoam_path,
    decode_foam_text,
    flatten_faces,
    is_time_directory,
    parse_boundary,
    parse_dimensioned_properties,
    parse_faces,
    parse_field,
    parse_label_list,
    parse_points,
    time_sort_key,
    unsafe_constructs,
)


class OpenFOAMNativeBackend:
    """Decode OpenFOAM ASCII mesh and field evidence without executing OpenFOAM."""

    backend_id = "openfoam.native"
    backend_version = "1.0.0"

    _MESH_PATHS = {
        "points": "constant/polyMesh/points",
        "faces": "constant/polyMesh/faces",
        "owner": "constant/polyMesh/owner",
        "neighbour": "constant/polyMesh/neighbour",
        "boundary": "constant/polyMesh/boundary",
    }
    _PROPERTY_PATHS = (
        "constant/transportProperties",
        "constant/physicalProperties",
        "constant/thermophysicalProperties",
    )

    def execute(self, request: InspectionExecutionRequest, context: ExecutionContext) -> dict[str, Any]:
        entries = {
            canonical_openfoam_path(entry.path): entry
            for entry in request.manifest.entries
            if not entry.is_dir and entry.path in set(request.plan.selected_paths)
        }
        actual_paths = {
            canonical_openfoam_path(entry.path): entry.path
            for entry in request.manifest.entries
            if not entry.is_dir and entry.path in set(request.plan.selected_paths)
        }
        text_cache: dict[str, DecodedFoamText] = {}
        degraded = False
        evidence_rows: list[dict[str, Any]] = []
        check_rows: list[dict[str, Any]] = []
        unsafe_rows: list[dict[str, Any]] = []

        def diagnostic(
            code: str,
            severity: DiagnosticSeverity,
            message: str,
            *,
            source_path: str | None = None,
            details: dict[str, Any] | None = None,
            fallback_used: str | None = None,
            information_lost: list[str] | None = None,
        ) -> DiagnosticEvent:
            event = DiagnosticEvent(
                code=code,
                severity=severity,
                message=message,
                source_path=source_path,
                details=details or {},
                parser="caereflex.openfoam_native",
                fallback_used=fallback_used,
                information_lost=information_lost or [],
            )
            context.diagnostics.append(event)
            return event

        def read_text(canonical_path: str) -> DecodedFoamText:
            if canonical_path in text_cache:
                return text_cache[canonical_path]
            actual = actual_paths.get(canonical_path)
            entry = entries.get(canonical_path)
            if actual is None or entry is None:
                raise OpenFOAMNativeError(f"OpenFOAM source file is absent from the execution plan: {canonical_path}")
            length = entry.size_bytes
            payload = context.read_bytes(actual, length=length)
            decoded = decode_foam_text(
                payload,
                actual,
                max_decompressed_bytes=max(1, request.plan.budget.max_bytes_read),
            )
            constructs = unsafe_constructs(decoded.text)
            for construct in constructs:
                row = {"source_path": actual, **construct}
                unsafe_rows.append(row)
                diagnostic(
                    "CRX-OF-NATIVE-UNSAFE-001",
                    DiagnosticSeverity.warning,
                    f"OpenFOAM {construct['kind']} was preserved but not expanded or executed.",
                    source_path=actual,
                    details=construct,
                    fallback_used="literal_source_only",
                    information_lost=["expanded_dictionary_value", "executed_code_result"],
                )
            text_cache[canonical_path] = decoded
            return decoded

        mesh_summary: dict[str, Any] = {
            "native_decoded": False,
            "point_count": None,
            "face_count": None,
            "internal_face_count": None,
            "boundary_face_count": None,
            "cell_count": None,
            "patch_count": None,
            "patches": [],
            "bounds": None,
            "array_ids": {},
        }
        mesh_started_at = utc_now_iso()
        mesh_clock = time.monotonic()
        mesh_diagnostics: list[DiagnosticEvent] = []
        missing_mesh = [path for path in self._MESH_PATHS.values() if path not in entries]
        if missing_mesh:
            degraded = True
            event = diagnostic(
                "CRX-OF-NATIVE-MESH-001",
                DiagnosticSeverity.warning,
                "Native OpenFOAM mesh decoding was skipped because required polyMesh files are missing.",
                details={"missing_paths": missing_mesh},
                fallback_used="structured_case_inventory",
                information_lost=["mesh_coordinates", "face_connectivity", "owner_neighbour_topology"],
            )
            mesh_diagnostics.append(event)
            context.record_attempt(
                ParserAttempt(
                    attempt_id=f"attempt_{uuid.uuid4().hex[:20]}",
                    stage="openfoam_native_mesh",
                    backend_id=self.backend_id,
                    backend_version=self.backend_version,
                    outcome=AttemptOutcome.skipped,
                    started_at=mesh_started_at,
                    completed_at=utc_now_iso(),
                    elapsed_seconds=time.monotonic() - mesh_clock,
                    fallback_to="openfoam.structured-inventory",
                    information_lost=event.information_lost,
                    diagnostics=mesh_diagnostics,
                    metadata={"missing_paths": missing_mesh},
                )
            )
        else:
            try:
                points = parse_points(read_text(self._MESH_PATHS["points"]).text)
                faces = parse_faces(read_text(self._MESH_PATHS["faces"]).text)
                owner = parse_label_list(read_text(self._MESH_PATHS["owner"]).text, "owner")
                neighbour = parse_label_list(read_text(self._MESH_PATHS["neighbour"]).text, "neighbour")
                patches = parse_boundary(read_text(self._MESH_PATHS["boundary"]).text)
                mesh = build_mesh(points, faces, owner, neighbour, patches)

                point_ref = context.register_numeric_array(
                    [component for point in mesh.points for component in point],
                    dtype="float64",
                    shape=(len(mesh.points), 3),
                    source_asset_id="asset_openfoam_mesh",
                    source_path=actual_paths[self._MESH_PATHS["points"]],
                    association="point",
                    component_names=["x", "y", "z"],
                    backend_version=self.backend_version,
                    metadata={"openfoam_object": "points", "native_ascii": True},
                )
                offsets, face_points = flatten_faces(mesh.faces)
                offsets_ref = context.register_numeric_array(
                    offsets,
                    dtype="int64",
                    shape=(len(offsets),),
                    source_asset_id="asset_openfoam_mesh",
                    source_path=actual_paths[self._MESH_PATHS["faces"]],
                    association="face",
                    backend_version=self.backend_version,
                    metadata={"openfoam_object": "face_offsets", "native_ascii": True},
                )
                face_points_ref = context.register_numeric_array(
                    face_points,
                    dtype="int64",
                    shape=(len(face_points),),
                    source_asset_id="asset_openfoam_mesh",
                    source_path=actual_paths[self._MESH_PATHS["faces"]],
                    association="face",
                    backend_version=self.backend_version,
                    metadata={"openfoam_object": "face_points", "native_ascii": True},
                )
                owner_ref = context.register_numeric_array(
                    mesh.owner,
                    dtype="int64",
                    shape=(len(mesh.owner),),
                    source_asset_id="asset_openfoam_mesh",
                    source_path=actual_paths[self._MESH_PATHS["owner"]],
                    association="face",
                    backend_version=self.backend_version,
                    metadata={"openfoam_object": "owner", "native_ascii": True},
                )
                neighbour_ref = context.register_numeric_array(
                    mesh.neighbour,
                    dtype="int64",
                    shape=(len(mesh.neighbour),),
                    source_asset_id="asset_openfoam_mesh",
                    source_path=actual_paths[self._MESH_PATHS["neighbour"]],
                    association="face",
                    backend_version=self.backend_version,
                    metadata={"openfoam_object": "neighbour", "native_ascii": True},
                )
                mesh_summary = {
                    "native_decoded": True,
                    "point_count": len(mesh.points),
                    "face_count": len(mesh.faces),
                    "internal_face_count": len(mesh.neighbour),
                    "boundary_face_count": len(mesh.faces) - len(mesh.neighbour),
                    "cell_count": mesh.cell_count,
                    "patch_count": len(mesh.patches),
                    "patches": mesh.patches,
                    "bounds": {
                        "minimum": list(mesh.bounds_min) if mesh.bounds_min is not None else None,
                        "maximum": list(mesh.bounds_max) if mesh.bounds_max is not None else None,
                    },
                    "array_ids": {
                        "points": point_ref.array_id,
                        "face_offsets": offsets_ref.array_id,
                        "face_points": face_points_ref.array_id,
                        "owner": owner_ref.array_id,
                        "neighbour": neighbour_ref.array_id,
                    },
                    "warnings": list(mesh.warnings),
                }
                for warning in mesh.warnings:
                    degraded = True
                    mesh_diagnostics.append(
                        diagnostic(
                            "CRX-OF-NATIVE-TOPOLOGY-001",
                            DiagnosticSeverity.warning,
                            warning,
                            source_path=actual_paths[self._MESH_PATHS["boundary"]],
                            information_lost=["fully_confirmed_topology"],
                        )
                    )
                context.record_attempt(
                    ParserAttempt(
                        attempt_id=f"attempt_{uuid.uuid4().hex[:20]}",
                        stage="openfoam_native_mesh",
                        backend_id=self.backend_id,
                        backend_version=self.backend_version,
                        outcome=AttemptOutcome.success,
                        started_at=mesh_started_at,
                        completed_at=utc_now_iso(),
                        elapsed_seconds=time.monotonic() - mesh_clock,
                        diagnostics=mesh_diagnostics,
                        metadata={
                            "point_count": len(mesh.points),
                            "face_count": len(mesh.faces),
                            "cell_count": mesh.cell_count,
                        },
                    )
                )
            except (OpenFOAMNativeError, OpenFOAMUnsupportedError, ExecutionContextError) as exc:
                degraded = True
                code = "CRX-OF-NATIVE-BINARY-001" if isinstance(exc, OpenFOAMUnsupportedError) else "CRX-OF-NATIVE-MESH-001"
                event = diagnostic(
                    code,
                    DiagnosticSeverity.warning,
                    f"Native OpenFOAM mesh decoding did not complete: {exc}",
                    details={"exception_type": type(exc).__name__},
                    fallback_used="structured_boundary_inventory",
                    information_lost=["mesh_coordinates", "face_connectivity", "owner_neighbour_topology"],
                )
                mesh_diagnostics.append(event)
                boundary_path = self._MESH_PATHS["boundary"]
                if boundary_path in entries:
                    try:
                        patches = parse_boundary(read_text(boundary_path).text)
                        mesh_summary["patches"] = patches
                        mesh_summary["patch_count"] = len(patches)
                        mesh_summary["boundary_face_count"] = sum(int(item["n_faces"]) for item in patches)
                    except OpenFOAMNativeError:
                        pass
                context.record_attempt(
                    ParserAttempt(
                        attempt_id=f"attempt_{uuid.uuid4().hex[:20]}",
                        stage="openfoam_native_mesh",
                        backend_id=self.backend_id,
                        backend_version=self.backend_version,
                        outcome=AttemptOutcome.failed,
                        started_at=mesh_started_at,
                        completed_at=utc_now_iso(),
                        elapsed_seconds=time.monotonic() - mesh_clock,
                        exception_type=type(exc).__name__,
                        exception_message=str(exc),
                        fallback_to="openfoam.structured-inventory",
                        information_lost=event.information_lost,
                        diagnostics=mesh_diagnostics,
                    )
                )
                context.record_attempt(
                    ParserAttempt(
                        attempt_id=f"attempt_{uuid.uuid4().hex[:20]}",
                        stage="openfoam_structured_inventory",
                        backend_id="openfoam.structured-inventory",
                        backend_version=self.backend_version,
                        outcome=AttemptOutcome.success,
                        started_at=utc_now_iso(),
                        completed_at=utc_now_iso(),
                        metadata={"patch_count": mesh_summary.get("patch_count")},
                    )
                )

        field_started_at = utc_now_iso()
        field_clock = time.monotonic()
        fields: list[dict[str, Any]] = []
        availability: dict[str, list[str]] = {}
        field_failures = 0
        field_entries: list[tuple[str, str]] = []
        for canonical, entry in entries.items():
            parts = PurePosixPath(canonical).parts
            if len(parts) != 2 or not is_time_directory(parts[0]):
                continue
            field_entries.append((canonical, parts[0]))
        field_entries.sort(key=lambda item: (time_sort_key(item[1]), item[0]))

        for canonical, time_name in field_entries:
            fallback_name = PurePosixPath(canonical).name
            try:
                decoded = read_text(canonical)
                field = parse_field(decoded.text, fallback_name=fallback_name)
                evidence = None
                check = None
                if field.dimensions_raw:
                    try:
                        evidence, check = build_openfoam_quantity_evidence(
                            field.name,
                            field.dimensions_raw,
                            context="field",
                            source_path=actual_paths[canonical],
                        )
                    except OpenFOAMQuantityError as exc:
                        degraded = True
                        diagnostic(
                            "CRX-UNITS-PARSE-001",
                            DiagnosticSeverity.warning,
                            f"OpenFOAM field {field.name!r} dimensions could not be parsed: {exc}",
                            source_path=actual_paths[canonical],
                            fallback_used="raw_dimension_text",
                            information_lost=["quantity_kind", "canonical_unit"],
                        )
                    else:
                        evidence_rows.append(evidence.model_dump(mode="json"))
                        check_rows.append(check.model_dump(mode="json"))
                else:
                    degraded = True
                    diagnostic(
                        "CRX-UNITS-MISSING-001",
                        DiagnosticSeverity.warning,
                        f"OpenFOAM field {field.name!r} has no dimensions declaration.",
                        source_path=actual_paths[canonical],
                        fallback_used="field_class_only",
                        information_lost=["quantity_kind", "canonical_unit"],
                    )

                array_id = None
                if field.internal_values and field.components is not None:
                    logical_count = {
                        "cell": mesh_summary.get("cell_count"),
                        "face": mesh_summary.get("face_count"),
                        "point": mesh_summary.get("point_count"),
                    }.get(field.association)
                    shape = (
                        (field.internal_count or 1, field.components)
                        if field.components > 1
                        else (field.internal_count or len(field.internal_values),)
                    )
                    ref = context.register_numeric_array(
                        field.internal_values,
                        dtype="float64",
                        shape=shape,
                        source_asset_id="asset_openfoam_case",
                        source_path=actual_paths[canonical],
                        association=field.association,
                        component_names=field.component_names,
                        quantity_evidence_ref=f"quantity:{actual_paths[canonical]}",
                        time_index=time_name,
                        backend_version=self.backend_version,
                        metadata={
                            "field_name": field.name,
                            "field_class": field.field_class,
                            "internal_mode": field.internal_mode,
                            "uniform": field.internal_mode == "uniform",
                            "logical_entity_count": logical_count,
                            "dimensions_raw": field.dimensions_raw,
                        },
                    )
                    array_id = ref.array_id
                elif field.internal_mode in {"unsupported", "missing"}:
                    degraded = True
                    diagnostic(
                        "CRX-OF-NATIVE-FIELD-001",
                        DiagnosticSeverity.warning,
                        f"Internal field values for {field.name!r} were preserved without numeric decoding.",
                        source_path=actual_paths[canonical],
                        details={"internal_mode": field.internal_mode, "raw_internal": field.raw_internal},
                        fallback_used="field_header_and_boundary_summary",
                        information_lost=["numeric_internal_field"],
                    )

                field_row = {
                    "name": field.name,
                    "time": time_name,
                    "source_path": actual_paths[canonical],
                    "field_class": field.field_class,
                    "association": field.association,
                    "components": field.components,
                    "component_names": field.component_names,
                    "dimensions_raw": field.dimensions_raw,
                    "quantity_kind": evidence.quantity_kind if evidence is not None else None,
                    "canonical_unit": evidence.normalized_unit if evidence is not None else None,
                    "internal_mode": field.internal_mode,
                    "internal_count": field.internal_count,
                    "array_id": array_id,
                    "boundary": field.boundary,
                    "unsafe_constructs": field.unsafe_constructs,
                }
                fields.append(field_row)
                availability.setdefault(time_name, []).append(field.name)
            except (OpenFOAMNativeError, OpenFOAMUnsupportedError, ExecutionContextError) as exc:
                degraded = True
                field_failures += 1
                code = "CRX-OF-NATIVE-BINARY-001" if isinstance(exc, OpenFOAMUnsupportedError) else "CRX-OF-NATIVE-FIELD-001"
                diagnostic(
                    code,
                    DiagnosticSeverity.warning,
                    f"OpenFOAM field {canonical!r} could not be decoded: {exc}",
                    source_path=actual_paths.get(canonical, canonical),
                    details={"exception_type": type(exc).__name__},
                    fallback_used="manifest_field_inventory",
                    information_lost=["numeric_internal_field", "boundary_field_details"],
                )
                availability.setdefault(time_name, []).append(fallback_name)

        for names in availability.values():
            names[:] = sorted(set(names))
        context.record_attempt(
            ParserAttempt(
                attempt_id=f"attempt_{uuid.uuid4().hex[:20]}",
                stage="openfoam_native_fields",
                backend_id=self.backend_id,
                backend_version=self.backend_version,
                outcome=AttemptOutcome.success if fields or not field_entries else AttemptOutcome.failed,
                started_at=field_started_at,
                completed_at=utc_now_iso(),
                elapsed_seconds=time.monotonic() - field_clock,
                fallback_to="openfoam.manifest-field-inventory" if field_failures else None,
                information_lost=["numeric_internal_field"] if field_failures else [],
                metadata={
                    "field_file_count": len(field_entries),
                    "decoded_field_count": len(fields),
                    "failed_field_count": field_failures,
                },
            )
        )

        material_started_at = utc_now_iso()
        material_clock = time.monotonic()
        materials: list[dict[str, Any]] = []
        material_failures = 0
        for canonical in self._PROPERTY_PATHS:
            if canonical not in entries:
                continue
            try:
                decoded = read_text(canonical)
                for row in parse_dimensioned_properties(decoded.text):
                    try:
                        evidence, check = parse_openfoam_dimensioned_value(
                            row["name"],
                            f"{row['dimensions']} {row['value']}",
                            context="material",
                            source_path=actual_paths[canonical],
                            line=int(row["line"]),
                        )
                    except OpenFOAMQuantityError as exc:
                        degraded = True
                        material_failures += 1
                        diagnostic(
                            "CRX-UNITS-PARSE-001",
                            DiagnosticSeverity.warning,
                            f"OpenFOAM property {row['name']!r} could not be interpreted: {exc}",
                            source_path=actual_paths[canonical],
                            details=row,
                            fallback_used="raw_dimensioned_property",
                            information_lost=["quantity_kind", "canonical_unit"],
                        )
                        materials.append({**row, "quantity_kind": None, "canonical_unit": None})
                        continue
                    evidence_rows.append(evidence.model_dump(mode="json"))
                    check_rows.append(check.model_dump(mode="json"))
                    materials.append(
                        {
                            **row,
                            "quantity_kind": evidence.quantity_kind,
                            "canonical_unit": evidence.normalized_unit,
                            "magnitude": evidence.magnitude,
                            "dimensional_status": check.status,
                        }
                    )
            except (OpenFOAMNativeError, OpenFOAMUnsupportedError, ExecutionContextError) as exc:
                degraded = True
                material_failures += 1
                diagnostic(
                    "CRX-OF-NATIVE-DICTIONARY-001",
                    DiagnosticSeverity.warning,
                    f"OpenFOAM property dictionary {canonical!r} could not be decoded: {exc}",
                    source_path=actual_paths.get(canonical, canonical),
                    fallback_used="manifest_dictionary_inventory",
                    information_lost=["dimensioned_material_properties"],
                )
        context.record_attempt(
            ParserAttempt(
                attempt_id=f"attempt_{uuid.uuid4().hex[:20]}",
                stage="openfoam_dimensioned_properties",
                backend_id=self.backend_id,
                backend_version=self.backend_version,
                outcome=AttemptOutcome.success if material_failures == 0 else AttemptOutcome.failed,
                started_at=material_started_at,
                completed_at=utc_now_iso(),
                elapsed_seconds=time.monotonic() - material_clock,
                fallback_to="openfoam.manifest-dictionary-inventory" if material_failures else None,
                information_lost=["dimensioned_material_properties"] if material_failures else [],
                metadata={"decoded_property_count": len(materials), "failed_dictionary_count": material_failures},
            )
        )

        discovered_times = {
            PurePosixPath(entry.path).parts[0]
            for entry in request.manifest.entries
            if PurePosixPath(entry.path).parts and is_time_directory(PurePosixPath(entry.path).parts[0])
        }
        discovered_times.update(availability)
        times = sorted(discovered_times, key=time_sort_key)
        if unsafe_rows:
            degraded = True

        summary = {
            "backend_id": self.backend_id,
            "backend_version": self.backend_version,
            "representation": "native OpenFOAM ASCII with literal-only dictionary handling",
            "mesh": mesh_summary,
            "times": times,
            "field_availability": {time_name: availability.get(time_name, []) for time_name in times},
            "fields": fields,
            "materials": materials,
            "unsafe_constructs": unsafe_rows,
            "source_files_read": list(context.paths_accessed),
            "bytes_read": context.bytes_read,
            "limitations": [
                "Binary OpenFOAM payloads are detected but not decoded in Gate 5B.",
                "Includes, substitutions, code streams, dynamic libraries, and coded boundary conditions are never expanded or executed.",
                "Decoded topology and fields are evidence extraction, not convergence, mesh-quality, or validation evidence.",
            ],
        }
        return {
            "_execution_status": "partial_success" if degraded else "success",
            "summary": summary,
            "quantity_evidence": evidence_rows,
            "dimensional_checks": check_rows,
        }
