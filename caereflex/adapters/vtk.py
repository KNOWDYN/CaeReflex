from __future__ import annotations
from pathlib import Path
import re
from caereflex.core.config import CaeReflexConfig
from caereflex.core.fingerprint import sha256_file, stable_case_id
from caereflex.core.models import (
    AdapterResult, AdapterStatus, ReflexCase, CaseType, InspectionStatus, TraceInfo,
    SourceKind, SourceFileRecord, HashStatus, EngineeringAsset, AssetType,
    ResultFieldRecord, FieldAssociation, FieldType, InspectionFlag, Severity, ProvenanceRecord
)
from caereflex.core.provenance import utc_now_iso
from caereflex.core.validation import safe_display_path
from .base import BaseAdapter


class VTKAdapter(BaseAdapter):
    name = "vtk_adapter"
    suffixes = {
        ".vtk", ".vtu", ".vtp", ".vti", ".vtr", ".vts",
        ".pvtu", ".pvtp", ".pvti", ".pvtr", ".pvts",
        ".pvd", ".vtm", ".vtmb",
    }

    def inspect(self, path: str | Path) -> AdapterResult:
        p = Path(path)
        workspace = p.parent if p.is_file() else p
        case = ReflexCase(
            case_id=stable_case_id(str(p.resolve()) if p.exists() else str(p)),
            case_name=p.stem if p.is_file() else p.name,
            case_type=CaseType.vtk,
            detected_formats=[],
            detected_tools=["VTK/ParaView-compatible"],
            physics_tags=["post-processing", "visualisation data"],
        )
        case.workspace.root_display = safe_display_path(workspace)
        case.provenance.append(ProvenanceRecord(event="vtk_inspection_started", details={"path": safe_display_path(p)}))
        if not p.exists():
            msg = "VTK path not found."
            case.inspection.status = InspectionStatus.failed
            case.inspection_flags.append(
                InspectionFlag(severity=Severity.error, category="path_not_found", message=msg)
            )
            return AdapterResult(adapter_name=self.name, status=AdapterStatus.failed, case=case, errors=[msg])

        files = [p] if p.is_file() else [
            item for item in p.rglob("*") if item.is_file() and item.suffix.lower() in self.suffixes
        ]
        for index, file_path in enumerate(files[: self.config.max_scan_files]):
            sha, hash_status = sha256_file(file_path, self.config.max_file_size_bytes)
            relative = safe_display_path(file_path, workspace)
            trace = TraceInfo(
                source_kind=SourceKind.extracted,
                source_files=[relative],
                adapter=self.name,
            )
            case.source_files.append(
                SourceFileRecord(
                    file_id=f"file_{index + 1}",
                    relative_path=relative,
                    suffix=file_path.suffix.lower(),
                    size_bytes=file_path.stat().st_size,
                    sha256=sha,
                    hash_status=HashStatus(hash_status),
                    trace=trace,
                )
            )
            suffix = file_path.suffix.lower()
            case.detected_formats.append(suffix)
            asset = EngineeringAsset(
                asset_id=f"asset_{len(case.assets) + 1}",
                asset_type=AssetType.result_file,
                name=file_path.name,
                properties={"standard_profile": "metadata-only"},
                trace=trace,
            )
            if suffix == ".vtk":
                self._inspect_legacy_vtk(file_path, case, asset, trace)
            else:
                category = "vtk_collection_metadata" if suffix in {".pvd", ".vtm", ".vtmb"} else "native_vtk_available_in_deep_profile"
                case.inspection_flags.append(
                    InspectionFlag(
                        severity=Severity.info,
                        category=category,
                        message=(
                            f"{suffix} was fingerprinted in the standard profile. "
                            "Use --profile deep or forensic for bounded native VTK inspection."
                        ),
                        trace=trace,
                    )
                )
            case.assets.append(asset)

        if not case.source_files:
            msg = "No VTK-compatible files detected."
            case.inspection.status = InspectionStatus.failed
            case.inspection_flags.append(
                InspectionFlag(severity=Severity.error, category="unsupported_format", message=msg)
            )
            return AdapterResult(adapter_name=self.name, status=AdapterStatus.unsupported, case=case, errors=[msg])

        case.detected_formats = sorted(set(case.detected_formats))
        case.inspection.status = InspectionStatus.partial_success if case.inspection_flags else InspectionStatus.success
        case.inspection.completed_at = utc_now_iso()
        case.agent_summary.summary = f"VTK-compatible result data inspected with {len(case.source_files)} file(s)."
        case.agent_summary.do_not_claim = [
            "Do not claim derived-field physics.",
            "Do not claim validation or design safety.",
            "Do not infer coordinate or field units without explicit evidence.",
        ]
        return AdapterResult(adapter_name=self.name, status=AdapterStatus(case.inspection.status.value), case=case)

    def _inspect_legacy_vtk(
        self,
        file_path: Path,
        case: ReflexCase,
        asset: EngineeringAsset,
        trace: TraceInfo,
    ) -> None:
        text = file_path.read_text(encoding="utf-8", errors="ignore")[:200000]
        dataset = re.search(r"DATASET\s+(\S+)", text)
        points = re.search(r"POINTS\s+(\d+)", text)
        cells = re.search(r"(?:CELLS|POLYGONS|LINES|VERTICES|TRIANGLE_STRIPS)\s+(\d+)", text)
        asset.metrics.update({
            "dataset_type": dataset.group(1) if dataset else None,
            "points": int(points.group(1)) if points else None,
            "cells": int(cells.group(1)) if cells else None,
        })
        for name in re.findall(r"SCALARS\s+(\S+)", text):
            case.result_fields.append(
                ResultFieldRecord(
                    name=name,
                    association=FieldAssociation.point,
                    field_type=FieldType.scalar,
                    components=1,
                    trace=trace,
                )
            )
        for name in re.findall(r"VECTORS\s+(\S+)", text):
            case.result_fields.append(
                ResultFieldRecord(
                    name=name,
                    association=FieldAssociation.point,
                    field_type=FieldType.vector,
                    components=3,
                    trace=trace,
                )
            )
