from __future__ import annotations
from pathlib import Path
import re

from caereflex.contracts import DiagnosticEvent, DiagnosticSeverity
from caereflex.core.config import CaeReflexConfig
from caereflex.core.fingerprint import sha256_file, stable_case_id
from caereflex.core.models import (
    AdapterResult, AdapterStatus, ReflexCase, CaseType, InspectionStatus, TraceInfo,
    SourceKind, SourceFileRecord, HashStatus, EngineeringAsset, AssetType,
    SolverRecord, BoundaryConditionRecord, MaterialPropertyRecord, NumericalSettingsRecord,
    ResultFieldRecord, FieldAssociation, FieldType, InspectionFlag, Severity, ProvenanceRecord
)
from caereflex.core.provenance import utc_now_iso
from caereflex.core.validation import safe_display_path
from caereflex.units import (
    OpenFOAMQuantityError,
    build_openfoam_quantity_evidence,
    diagnostic_from_check,
    parse_openfoam_dimensioned_value,
    serialise_dimension_vector,
)
from .base import BaseAdapter


class OpenFOAMAdapter(BaseAdapter):
    name = "openfoam_adapter"
    expected = [
        "system/controlDict", "system/fvSchemes", "system/fvSolution",
        "constant/transportProperties", "constant/turbulenceProperties",
        "constant/polyMesh/boundary",
    ]

    def inspect(self, path: str | Path) -> AdapterResult:
        root = Path(path)
        case_id = stable_case_id(str(root.resolve()) if root.exists() else str(root))
        case = ReflexCase(
            case_id=case_id,
            case_name=root.name,
            case_type=CaseType.openfoam,
            detected_formats=["OpenFOAM case folder"],
            detected_tools=["OpenFOAM"],
            physics_tags=["CFD", "finite volume"],
        )
        case.workspace.root_display = safe_display_path(root)
        case.provenance.append(ProvenanceRecord(event="openfoam_inspection_started", details={"path": safe_display_path(root)}))
        if not root.exists() or not root.is_dir():
            msg = "OpenFOAM path not found or not a directory."
            case.inspection.status = InspectionStatus.failed
            case.inspection_flags.append(InspectionFlag(severity=Severity.error, category="path_not_found", message=msg))
            return AdapterResult(adapter_name=self.name, status=AdapterStatus.failed, case=case, errors=[msg])

        files: list[Path] = []
        for rel in self.expected:
            file_path = root / rel
            if file_path.exists():
                files.append(file_path)
            else:
                case.inspection_flags.append(
                    InspectionFlag(
                        severity=Severity.warning,
                        category="missing_expected_file",
                        message=f"Missing expected OpenFOAM file: {rel}",
                    )
                )
        zero_dir = root / "0"
        if zero_dir.exists():
            files.extend(file_path for file_path in zero_dir.iterdir() if file_path.is_file())
        for candidate in [root / "log", root / "log.simpleFoam", root / "postProcessing"]:
            if candidate.exists():
                if candidate.is_file():
                    files.append(candidate)
                else:
                    files.extend([file_path for file_path in candidate.rglob("*") if file_path.is_file()][:20])

        for index, file_path in enumerate(dict.fromkeys(files)):
            sha, hash_status = sha256_file(file_path, self.config.max_file_size_bytes)
            relative = safe_display_path(file_path, root)
            trace = TraceInfo(source_kind=SourceKind.extracted, source_files=[relative], adapter=self.name)
            case.source_files.append(
                SourceFileRecord(
                    file_id=f"file_{index + 1}",
                    relative_path=relative,
                    suffix=file_path.suffix or None,
                    size_bytes=file_path.stat().st_size,
                    sha256=sha,
                    hash_status=HashStatus(hash_status),
                    trace=trace,
                )
            )
            self._parse_file(root, file_path, case, trace)

        case.assets.append(
            EngineeringAsset(
                asset_id="asset_openfoam_case",
                asset_type=AssetType.case_folder,
                name=root.name,
                metrics={
                    "source_files": len(case.source_files),
                    "quantity_evidence": len(case.quantity_evidence),
                    "dimensional_checks": len(case.dimensional_checks),
                },
                trace=TraceInfo(
                    source_kind=SourceKind.extracted,
                    source_files=[safe_display_path(root)],
                    adapter=self.name,
                ),
            )
        )
        if not case.source_files:
            msg = "No OpenFOAM case files detected."
            case.inspection.status = InspectionStatus.failed
            case.inspection_flags.append(InspectionFlag(severity=Severity.error, category="unsupported_format", message=msg))
            return AdapterResult(adapter_name=self.name, status=AdapterStatus.unsupported, case=case, errors=[msg])
        case.inspection.status = InspectionStatus.partial_success if case.inspection_flags else InspectionStatus.success
        case.inspection.completed_at = utc_now_iso()
        case.agent_summary.summary = (
            f"OpenFOAM case inspected. {len(case.source_files)} files were considered and "
            f"{len(case.quantity_evidence)} dimensioned quantities were recorded."
        )
        case.agent_summary.do_not_claim = [
            "Do not claim convergence.",
            "Do not claim mesh adequacy.",
            "Do not claim validation or certification.",
            "Do not treat unresolved or conflicted dimensions as confirmed physical semantics.",
        ]
        return AdapterResult(adapter_name=self.name, status=AdapterStatus(case.inspection.status.value), case=case)

    def _parse_dict_entries(self, text: str) -> dict[str, str]:
        entries: dict[str, str] = {}
        for match in re.finditer(r"^\s*([A-Za-z0-9_]+)\s+([^;{}]+);", text, flags=re.MULTILINE):
            entries[match.group(1)] = match.group(2).strip()
        return entries

    def _parse_foamfile_header(self, text: str) -> dict[str, str]:
        match = re.search(r"\bFoamFile\s*\{(.*?)\}", text, flags=re.DOTALL)
        if not match:
            return {}
        return {
            item.group(1): item.group(2).strip()
            for item in re.finditer(r"\b([A-Za-z0-9_]+)\s+([^;{}]+);", match.group(1))
        }

    def _field_type(self, field_class: str | None, field_name: str) -> tuple[FieldType, int | None, str]:
        class_name = field_class or ""
        if "SphericalTensorField" in class_name:
            return FieldType.tensor, 1, "class_header"
        if "SymmTensorField" in class_name:
            return FieldType.tensor, 6, "class_header"
        if "TensorField" in class_name:
            return FieldType.tensor, 9, "class_header"
        if "VectorField" in class_name:
            return FieldType.vector, 3, "class_header"
        if "ScalarField" in class_name:
            return FieldType.scalar, 1, "class_header"
        if field_name == "U":
            return FieldType.vector, 3, "name_fallback"
        return FieldType.unknown, None, "unresolved"

    def _line_number(self, text: str, offset: int) -> int:
        return text.count("\n", 0, offset) + 1

    def _record_quantity(self, case: ReflexCase, evidence: object, check: object, trace: TraceInfo) -> None:
        evidence_dict = evidence.model_dump(mode="json")  # type: ignore[attr-defined]
        check_dict = check.model_dump(mode="json")  # type: ignore[attr-defined]
        case.quantity_evidence.append(evidence_dict)
        case.dimensional_checks.append(check_dict)
        diagnostic = diagnostic_from_check(check)  # type: ignore[arg-type]
        if diagnostic is not None:
            case.diagnostics.append(diagnostic.model_dump(mode="json"))
        if check_dict.get("blocks_automated_interpretation"):
            case.inspection_flags.append(
                InspectionFlag(
                    severity=Severity.warning,
                    category="dimension_mismatch",
                    message=check_dict["message"],
                    trace=trace,
                )
            )

    def _record_units_parse_failure(self, case: ReflexCase, relative: str, subject: str, raw: str, error: Exception, trace: TraceInfo) -> None:
        diagnostic = DiagnosticEvent(
            code="CRX-UNITS-PARSE-001",
            severity=DiagnosticSeverity.warning,
            message=f"Could not parse dimensions for {subject!r}; the raw source value was preserved.",
            source_path=relative,
            details={"subject_name": subject, "raw_value": raw, "error": str(error)},
            parser="caereflex.units.openfoam",
            fallback_used="raw_text",
            information_lost=["canonical_unit", "quantity_kind", "dimensional_consistency"],
        )
        case.diagnostics.append(diagnostic.model_dump(mode="json"))
        case.inspection_flags.append(
            InspectionFlag(
                severity=Severity.warning,
                category="units_parse_failure",
                message=diagnostic.message,
                trace=trace,
            )
        )

    def _parse_file(self, root: Path, file_path: Path, case: ReflexCase, trace: TraceInfo) -> None:
        relative = safe_display_path(file_path, root)
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        entries = self._parse_dict_entries(text)
        header = self._parse_foamfile_header(text)
        if relative == "system/controlDict":
            case.solver_records.append(
                SolverRecord(
                    application=entries.get("application") or header.get("application"),
                    start_time=entries.get("startTime"),
                    end_time=entries.get("endTime"),
                    metadata={**header, **entries},
                    trace=trace,
                )
            )
        elif relative in {"system/fvSchemes", "system/fvSolution"}:
            for key, value in entries.items():
                case.numerical_settings.append(NumericalSettingsRecord(category=Path(relative).name, name=key, value=value, trace=trace))
        elif relative == "constant/transportProperties":
            for key, value in entries.items():
                if not value.lstrip().startswith("["):
                    case.materials.append(MaterialPropertyRecord(name=key, value=value, metadata={"units_status": "not_dimensioned"}, trace=trace))
                    continue
                line_match = re.search(rf"^\s*{re.escape(key)}\s+", text, flags=re.MULTILINE)
                line = self._line_number(text, line_match.start()) if line_match else None
                try:
                    evidence, check = parse_openfoam_dimensioned_value(
                        key,
                        value,
                        context="material",
                        source_path=relative,
                        line=line,
                    )
                except OpenFOAMQuantityError as exc:
                    case.materials.append(MaterialPropertyRecord(name=key, value=value, metadata={"units_status": "parse_failed"}, trace=trace))
                    self._record_units_parse_failure(case, relative, key, value, exc, trace)
                    continue
                case.materials.append(
                    MaterialPropertyRecord(
                        name=key,
                        value=evidence.magnitude if evidence.magnitude is not None else value,
                        units=evidence.normalized_unit,
                        metadata={
                            "raw_value": evidence.raw_value,
                            "dimension_vector": serialise_dimension_vector(evidence.dimension_vector or (0, 0, 0, 0, 0, 0, 0)),
                            "quantity_kind": evidence.quantity_kind,
                            "evidence_state": evidence.evidence_state,
                            "units_status": check.status,
                        },
                        trace=trace,
                    )
                )
                self._record_quantity(case, evidence, check, trace)
        elif relative == "constant/turbulenceProperties":
            for key, value in entries.items():
                case.numerical_settings.append(NumericalSettingsRecord(category="turbulenceProperties", name=key, value=value, trace=trace))
        elif relative == "constant/polyMesh/boundary":
            patches = re.findall(r"\n\s*([A-Za-z0-9_]+)\s*\{\s*type\s+([^;]+);", text)
            for patch, patch_type in patches:
                case.boundary_conditions.append(BoundaryConditionRecord(patch=patch, type=patch_type.strip(), trace=trace))
        elif relative.startswith("0/"):
            field_name = Path(relative).name
            field_class = header.get("class") or entries.get("class")
            field_type, components, type_source = self._field_type(field_class, field_name)
            metadata = {
                "field_class": field_class,
                "field_type_source": type_source,
                "object": header.get("object"),
            }
            dimensions_match = re.search(r"^\s*dimensions\s+(\[[^\]]+\])\s*;", text, flags=re.MULTILINE)
            if dimensions_match:
                raw_dimensions = dimensions_match.group(1)
                line = self._line_number(text, dimensions_match.start())
                try:
                    evidence, check = build_openfoam_quantity_evidence(
                        field_name,
                        raw_dimensions,
                        context="field",
                        source_path=relative,
                        line=line,
                    )
                except OpenFOAMQuantityError as exc:
                    metadata["dimensions_raw"] = raw_dimensions
                    metadata["units_status"] = "parse_failed"
                    self._record_units_parse_failure(case, relative, field_name, raw_dimensions, exc, trace)
                else:
                    metadata.update(
                        {
                            "dimensions": serialise_dimension_vector(evidence.dimension_vector or (0, 0, 0, 0, 0, 0, 0)),
                            "canonical_unit": evidence.normalized_unit,
                            "quantity_kind": evidence.quantity_kind,
                            "units_status": check.status,
                        }
                    )
                    self._record_quantity(case, evidence, check, trace)
            else:
                diagnostic = DiagnosticEvent(
                    code="CRX-UNITS-MISSING-001",
                    severity=DiagnosticSeverity.warning,
                    message=f"OpenFOAM field {field_name!r} has no parseable dimensions declaration.",
                    source_path=relative,
                    details={"field_class": field_class},
                    parser="caereflex.units.openfoam",
                    fallback_used="field_class_only",
                    information_lost=["canonical_unit", "quantity_kind", "dimensional_consistency"],
                )
                case.diagnostics.append(diagnostic.model_dump(mode="json"))
                case.inspection_flags.append(InspectionFlag(severity=Severity.warning, category="units_dimensions_missing", message=diagnostic.message, trace=trace))
                metadata["units_status"] = "missing"

            case.result_fields.append(
                ResultFieldRecord(
                    name=field_name,
                    association=FieldAssociation.volume,
                    field_type=field_type,
                    components=components,
                    metadata=metadata,
                    trace=trace,
                )
            )
            for patch, body in re.findall(r"\n\s*([A-Za-z0-9_]+)\s*\{([^{}]*type\s+[^;]+;[^{}]*)\}", text, flags=re.DOTALL):
                patch_type = re.search(r"type\s+([^;]+);", body)
                value = re.search(r"value\s+([^;]+);", body)
                case.boundary_conditions.append(
                    BoundaryConditionRecord(
                        patch=patch,
                        field=field_name,
                        type=patch_type.group(1).strip() if patch_type else None,
                        value=value.group(1).strip() if value else None,
                        trace=trace,
                    )
                )
        if "Solving for" in text or "Initial residual" in text:
            case.inspection_flags.append(
                InspectionFlag(
                    severity=Severity.info,
                    category="residual_like_lines_detected",
                    message=f"Residual-like solver log lines detected in {relative}.",
                    trace=trace,
                )
            )
