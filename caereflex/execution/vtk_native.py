"""Optional-reader and orchestration layer for native VTK inspection."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import xml.etree.ElementTree as ET

from caereflex.contracts import AttemptOutcome, DiagnosticEvent, DiagnosticSeverity, InspectionExecutionRequest
from caereflex.core.provenance import utc_now_iso
from caereflex.execution.context import ExecutionContext, ExecutionContextError
from caereflex.execution.vtk_common import (
    VTKNativeError, _PARALLEL_SUFFIXES, _COLLECTION_SUFFIXES, _VTK_SUFFIXES,
    _MESHIO_CELL_TO_VTK, _attempt, _finite, _fingerprint, _register_dataset, _array_record,
)
from caereflex.execution.vtk_legacy import parse_legacy_ascii
from caereflex.execution.vtk_xml import parse_xml_dataset, xml_inventory


def _to_list(values: Any) -> list[Any]:
    if hasattr(values, "ravel"):
        values = values.ravel()
    if hasattr(values, "tolist"):
        values = values.tolist()
    if isinstance(values, list):
        result: list[Any] = []
        for item in values:
            result.extend(item if isinstance(item, list) else [item])
        return result
    return list(values)


def _numpy_dtype_name(values: Any) -> str:
    kind = getattr(getattr(values, "dtype", None), "kind", None)
    itemsize = int(getattr(getattr(values, "dtype", None), "itemsize", 8) or 8)
    if kind == "b":
        return "bool"
    if kind == "u":
        return f"uint{itemsize * 8}"
    if kind == "i":
        return f"int{itemsize * 8}"
    return "float32" if itemsize <= 4 else "float64"


def _optional_fields(container: Any, association: str) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for name in getattr(container, "keys", lambda: [])():
        values = container[name]
        shape = tuple(int(item) for item in getattr(values, "shape", (len(values),)))
        tuples = shape[0] if shape else 1
        components = shape[1] if len(shape) > 1 else 1
        flattened = _to_list(values)
        if not all(isinstance(value, (bool, int, float)) for value in flattened):
            continue
        fields.append(_array_record(
            name=str(name), association=association, components=components, tuples=tuples,
            dtype=_numpy_dtype_name(values), values=_finite(flattened), role="optional_reader_data",
        ))
    return fields


def _pyvista_summary(
    staged_path: Path,
    context: ExecutionContext,
    source_path: str,
    asset_id: str,
    backend_version: str,
) -> dict[str, Any]:
    try:
        import pyvista as pv  # type: ignore
    except Exception as exc:
        raise ModuleNotFoundError("pyvista/vtk is not installed") from exc
    dataset = pv.read(str(staged_path))
    if hasattr(dataset, "n_blocks"):
        raise VTKNativeError("PyVista multiblock results remain collection inventories in Gate 5D.")
    points_values = _to_list(getattr(dataset, "points", []))
    point_count = int(getattr(dataset, "n_points", len(points_values) // 3))
    cell_count = int(getattr(dataset, "n_cells", 0))
    cell_types = [int(value) for value in _to_list(getattr(dataset, "celltypes", []))]
    connectivity: list[int] = []
    offsets: list[int] = []
    if hasattr(dataset, "cell_connectivity") and hasattr(dataset, "offset"):
        connectivity = [int(value) for value in _to_list(dataset.cell_connectivity)]
        raw_offsets = [int(value) for value in _to_list(dataset.offset)]
        offsets = raw_offsets[1:] if len(raw_offsets) == cell_count + 1 and raw_offsets[:1] == [0] else raw_offsets
    elif hasattr(dataset, "cells"):
        raw = [int(value) for value in _to_list(dataset.cells)]
        cursor = 0
        while cursor < len(raw):
            count = raw[cursor]
            cursor += 1
            connectivity.extend(raw[cursor:cursor + count])
            cursor += count
            offsets.append(len(connectivity))
    raw_bounds = list(dataset.bounds)
    parsed = {
        "dataset_type": type(dataset).__name__,
        "points": _finite(points_values),
        "points_dtype": _numpy_dtype_name(getattr(dataset, "points", [])),
        "point_count": point_count,
        "connectivity": connectivity,
        "offsets": offsets,
        "cell_types": cell_types,
        "cell_count": cell_count,
        "fields": [
            *_optional_fields(dataset.point_data, "point"),
            *_optional_fields(dataset.cell_data, "cell"),
            *_optional_fields(dataset.field_data, "field"),
        ],
        "bounds": [
            [float(raw_bounds[0]), float(raw_bounds[1])],
            [float(raw_bounds[2]), float(raw_bounds[3])],
            [float(raw_bounds[4]), float(raw_bounds[5])],
        ],
        "encoding": "optional-pyvista",
        "byte_order": "native",
    }
    return _register_dataset(
        parsed, context, source_path=source_path, asset_id=asset_id,
        backend_version=backend_version, reader="vtk.pyvista",
    )


def _meshio_summary(
    staged_path: Path,
    context: ExecutionContext,
    source_path: str,
    asset_id: str,
    backend_version: str,
) -> dict[str, Any]:
    try:
        import meshio  # type: ignore
    except Exception as exc:
        raise ModuleNotFoundError("meshio is not installed") from exc
    mesh = meshio.read(str(staged_path))
    points = _to_list(mesh.points)
    connectivity: list[int] = []
    offsets: list[int] = []
    cell_types: list[int] = []
    for block in mesh.cells:
        vtk_type = _MESHIO_CELL_TO_VTK.get(str(block.type))
        for row in block.data:
            values = [int(value) for value in _to_list(row)]
            connectivity.extend(values)
            offsets.append(len(connectivity))
            cell_types.append(vtk_type or 0)
    fields = [*_optional_fields(mesh.point_data, "point")]
    for name, blocks in mesh.cell_data.items():
        flattened: list[Any] = []
        tuples = 0
        components = 1
        dtype = "float64"
        for block in blocks:
            values = _to_list(block)
            flattened.extend(values)
            shape = tuple(int(item) for item in getattr(block, "shape", (len(block),)))
            tuples += shape[0] if shape else 1
            components = shape[1] if len(shape) > 1 else components
            dtype = _numpy_dtype_name(block)
        if flattened and all(isinstance(value, (bool, int, float)) for value in flattened):
            fields.append(_array_record(
                name=str(name), association="cell", components=components, tuples=tuples,
                dtype=dtype, values=_finite(flattened), role="meshio_cell_data",
            ))
    parsed = {
        "dataset_type": "meshio.Mesh",
        "points": _finite(points),
        "points_dtype": _numpy_dtype_name(mesh.points),
        "point_count": len(mesh.points),
        "connectivity": connectivity,
        "offsets": offsets,
        "cell_types": cell_types,
        "cell_count": len(offsets),
        "fields": fields,
        "encoding": "optional-meshio",
        "byte_order": "native",
    }
    return _register_dataset(
        parsed, context, source_path=source_path, asset_id=asset_id,
        backend_version=backend_version, reader="vtk.meshio",
    )


def _core_summary(
    payload: bytes,
    suffix: str,
    context: ExecutionContext,
    source_path: str,
    asset_id: str,
    backend_version: str,
) -> dict[str, Any]:
    parsed = parse_legacy_ascii(payload) if suffix == ".vtk" else parse_xml_dataset(payload)
    return _register_dataset(
        parsed, context, source_path=source_path, asset_id=asset_id,
        backend_version=backend_version, reader="vtk.core",
    )


class VTKNativeBackend:
    backend_id = "vtk.native"
    backend_version = "1.0.0"

    def execute(self, request: InspectionExecutionRequest, context: ExecutionContext) -> dict[str, Any]:
        selected = [path for path in request.plan.selected_paths if Path(path).suffix.lower() in _VTK_SUFFIXES]
        selected_set = set(selected)
        summary: dict[str, Any] = {
            "format": "VTK",
            "reader": self.backend_id,
            "files": [],
            "dataset_count": 0,
            "collection_count": 0,
            "parallel_inventory_count": 0,
            "time_values": [],
            "non_execution_guarantees": [
                "collection references are inventoried but never fetched outside selected paths",
                "ParaView and external programs are never launched",
                "source files are never modified",
            ],
        }
        payloads: dict[str, bytes] = {}
        staged: dict[str, Path] = {}
        for path in selected:
            started = utc_now_iso()
            try:
                payload = context.read_bytes(path)
                payloads[path] = payload
                target = context.work_root / "vtk-inputs" / PurePosixPath(path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                staged[path] = target
                _attempt(
                    context, stage="read_source", backend_id=self.backend_id,
                    outcome=AttemptOutcome.success, started_at=started,
                )
            except (ExecutionContextError, OSError) as exc:
                diagnostic = DiagnosticEvent(
                    code="CRX-VTK-READ-001",
                    severity=DiagnosticSeverity.warning,
                    message=f"VTK source could not be read within the execution budget: {exc}",
                    source_path=path,
                    parser=self.backend_id,
                    information_lost=["dataset_evidence"],
                )
                _attempt(
                    context, stage="read_source", backend_id=self.backend_id,
                    outcome=AttemptOutcome.failed, started_at=started, error=exc,
                    diagnostics=[diagnostic], information_lost=["dataset_evidence"],
                )
        for index, path in enumerate(selected, start=1):
            if path not in payloads:
                continue
            payload = payloads[path]
            suffix = Path(path).suffix.lower()
            asset_id = f"asset_vtk_{index}"
            if suffix in _COLLECTION_SUFFIXES or suffix in _PARALLEL_SUFFIXES:
                started = utc_now_iso()
                try:
                    file_summary = xml_inventory(payload, path, selected_set)
                    unsafe = [item for item in file_summary["references"] if not item["safe"]]
                    missing = [item for item in file_summary["references"] if item["safe"] and not item["selected"]]
                    diagnostics: list[DiagnosticEvent] = []
                    if unsafe or missing:
                        diagnostics.append(DiagnosticEvent(
                            code="CRX-VTK-COLLECTION-REFERENCE-001",
                            severity=DiagnosticSeverity.warning,
                            message="VTK collection or parallel references were inventoried but some were unsafe or absent from the selected manifest.",
                            source_path=path,
                            parser="vtk.xml-inventory",
                            details={"unsafe_count": len(unsafe), "unselected_count": len(missing)},
                            information_lost=["referenced_dataset_values"],
                        ))
                    _attempt(
                        context, stage="xml_reference_inventory", backend_id="vtk.xml-inventory",
                        outcome=AttemptOutcome.success, started_at=started, diagnostics=diagnostics,
                        metadata={"external_references_loaded": False},
                    )
                    summary["files"].append(file_summary)
                    summary["time_values"].extend(file_summary.get("time_values", []))
                    if suffix in _COLLECTION_SUFFIXES:
                        summary["collection_count"] += 1
                    else:
                        summary["parallel_inventory_count"] += 1
                except (VTKNativeError, ET.ParseError) as exc:
                    diagnostic = DiagnosticEvent(
                        code="CRX-VTK-CORE-FALLBACK-001",
                        severity=DiagnosticSeverity.warning,
                        message=f"VTK collection inventory fell back to a fingerprint: {exc}",
                        source_path=path,
                        parser="vtk.xml-inventory",
                        fallback_used="fingerprint-only",
                        information_lost=["references", "time_values"],
                    )
                    _attempt(
                        context, stage="xml_reference_inventory", backend_id="vtk.xml-inventory",
                        outcome=AttemptOutcome.failed, started_at=started, error=exc,
                        fallback_to="fingerprint-only", information_lost=["references", "time_values"],
                        diagnostics=[diagnostic],
                    )
                    summary["files"].append(_fingerprint(payload, path, suffix))
                continue
            summary["dataset_count"] += 1
            file_summary: dict[str, Any] | None = None
            if request.backend_options.get("disable_pyvista") is True:
                _attempt(
                    context, stage="pyvista_decode", backend_id="vtk.pyvista",
                    outcome=AttemptOutcome.skipped, started_at=utc_now_iso(),
                    fallback_to="vtk.meshio", metadata={"reason": "disabled_by_request"},
                )
            else:
                started = utc_now_iso()
                try:
                    file_summary = _pyvista_summary(
                        staged[path], context, path, asset_id, self.backend_version,
                    )
                    _attempt(
                        context, stage="pyvista_decode", backend_id="vtk.pyvista",
                        outcome=AttemptOutcome.success, started_at=started,
                    )
                except ModuleNotFoundError as exc:
                    _attempt(
                        context, stage="pyvista_decode", backend_id="vtk.pyvista",
                        outcome=AttemptOutcome.skipped, started_at=started, error=exc,
                        fallback_to="vtk.meshio", metadata={"reason": "optional_dependency_unavailable"},
                    )
                except Exception as exc:
                    diagnostic = DiagnosticEvent(
                        code="CRX-VTK-PYVISTA-FALLBACK-001",
                        severity=DiagnosticSeverity.info,
                        message=f"PyVista/VTK did not decode {path}; meshio was tried next: {exc}",
                        source_path=path,
                        parser="vtk.pyvista",
                        fallback_used="vtk.meshio",
                    )
                    _attempt(
                        context, stage="pyvista_decode", backend_id="vtk.pyvista",
                        outcome=AttemptOutcome.failed, started_at=started, error=exc,
                        fallback_to="vtk.meshio", diagnostics=[diagnostic],
                    )
            if file_summary is None:
                if request.backend_options.get("disable_meshio") is True:
                    _attempt(
                        context, stage="meshio_decode", backend_id="vtk.meshio",
                        outcome=AttemptOutcome.skipped, started_at=utc_now_iso(),
                        fallback_to="vtk.core", metadata={"reason": "disabled_by_request"},
                    )
                else:
                    started = utc_now_iso()
                    try:
                        file_summary = _meshio_summary(
                            staged[path], context, path, asset_id, self.backend_version,
                        )
                        _attempt(
                            context, stage="meshio_decode", backend_id="vtk.meshio",
                            outcome=AttemptOutcome.success, started_at=started,
                        )
                    except ModuleNotFoundError as exc:
                        _attempt(
                            context, stage="meshio_decode", backend_id="vtk.meshio",
                            outcome=AttemptOutcome.skipped, started_at=started, error=exc,
                            fallback_to="vtk.core", metadata={"reason": "optional_dependency_unavailable"},
                        )
                    except Exception as exc:
                        diagnostic = DiagnosticEvent(
                            code="CRX-VTK-MESHIO-FALLBACK-001",
                            severity=DiagnosticSeverity.info,
                            message=f"meshio did not decode {path}; the bounded core VTK reader was tried next: {exc}",
                            source_path=path,
                            parser="vtk.meshio",
                            fallback_used="vtk.core",
                        )
                        _attempt(
                            context, stage="meshio_decode", backend_id="vtk.meshio",
                            outcome=AttemptOutcome.failed, started_at=started, error=exc,
                            fallback_to="vtk.core", diagnostics=[diagnostic],
                        )
            if file_summary is None:
                started = utc_now_iso()
                try:
                    file_summary = _core_summary(
                        payload, suffix, context, path, asset_id, self.backend_version,
                    )
                    _attempt(
                        context, stage="core_decode", backend_id="vtk.core",
                        outcome=AttemptOutcome.success, started_at=started,
                    )
                except (UnicodeDecodeError, VTKNativeError, ExecutionContextError, ET.ParseError) as exc:
                    encoding_limited = suffix != ".vtk" and any(
                        word in str(exc).lower() for word in ("appended", "compressed", "binary")
                    )
                    diagnostic = DiagnosticEvent(
                        code="CRX-VTK-XML-ENCODING-001" if encoding_limited else "CRX-VTK-CORE-FALLBACK-001",
                        severity=DiagnosticSeverity.warning,
                        message=f"Bounded VTK decoding fell back to a fingerprint: {exc}",
                        source_path=path,
                        parser="vtk.core",
                        fallback_used="fingerprint-only",
                        information_lost=["points", "cells", "fields", "lazy_arrays"],
                    )
                    _attempt(
                        context, stage="core_decode", backend_id="vtk.core",
                        outcome=AttemptOutcome.failed, started_at=started, error=exc,
                        fallback_to="fingerprint-only",
                        information_lost=["points", "cells", "fields", "lazy_arrays"],
                        diagnostics=[diagnostic],
                    )
                    file_summary = _fingerprint(payload, path, suffix)
            summary["files"].append(file_summary)
        summary["time_values"] = sorted(set(float(value) for value in summary["time_values"]))
        summary["time_step_count"] = len(summary["time_values"])
        summary["array_count"] = len(context.arrays)
        summary["diagnostic_count"] = len(context.diagnostics)
        return {"summary": summary}


__all__ = ["VTKNativeBackend"]
