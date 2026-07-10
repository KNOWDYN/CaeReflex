"""Read-only OpenFOAM native-format inspection backend.

The reader decodes bounded ASCII ``polyMesh`` and field files inside the Gate 5A
worker. It never expands directives, executes code, loads OpenFOAM libraries or runs
solver utilities. Binary and unsupported grammar features fall back to metadata with
stable diagnostics.
"""
from __future__ import annotations

import math
import re
import time
import uuid
from pathlib import PurePosixPath
from typing import Any, Iterable

from caereflex.contracts import (
    AttemptOutcome,
    DiagnosticEvent,
    DiagnosticSeverity,
    InspectionExecutionRequest,
    ParserAttempt,
)
from caereflex.core.provenance import utc_now_iso
from caereflex.execution.context import ExecutionContext, ExecutionContextError


class OpenFOAMNativeError(RuntimeError):
    """Raised when a native OpenFOAM construct cannot be decoded safely."""


_HEADER_RE = re.compile(r"\bFoamFile\s*\{(.*?)\}", re.DOTALL)
_ENTRY_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s+([^;{}]+);")
_DIRECTIVE_RE = re.compile(r"^\s*#(?:include|includeEtc|codeStream|calc|eval|remove|inputMode)\b", re.MULTILINE)
_TIME_RE = re.compile(r"^(?:0|[1-9]\d*)(?:\.\d+)?$")
_FIELD_COMPONENTS = {
    "volScalarField": (1, []),
    "surfaceScalarField": (1, []),
    "pointScalarField": (1, []),
    "volVectorField": (3, ["x", "y", "z"]),
    "surfaceVectorField": (3, ["x", "y", "z"]),
    "pointVectorField": (3, ["x", "y", "z"]),
    "volSphericalTensorField": (1, ["ii"]),
    "volSymmTensorField": (6, ["xx", "xy", "xz", "yy", "yz", "zz"]),
    "volTensorField": (9, ["xx", "xy", "xz", "yx", "yy", "yz", "zx", "zy", "zz"]),
}


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def _header(text: str) -> dict[str, str]:
    match = _HEADER_RE.search(text)
    if not match:
        return {}
    return {item.group(1): item.group(2).strip() for item in _ENTRY_RE.finditer(match.group(1))}


def _payload_after_header(text: str) -> str:
    match = _HEADER_RE.search(text)
    return text[match.end():] if match else text


def _counted_body(text: str) -> tuple[int, str]:
    clean = _strip_comments(_payload_after_header(text))
    match = re.search(r"\b(\d+)\s*\(", clean)
    if not match:
        raise OpenFOAMNativeError("No counted OpenFOAM list was found.")
    count = int(match.group(1))
    opening = clean.find("(", match.start())
    depth = 0
    for index in range(opening, len(clean)):
        char = clean[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return count, clean[opening + 1:index]
    raise OpenFOAMNativeError("Counted OpenFOAM list is not closed.")


def _floats(text: str) -> list[float]:
    try:
        values = [float(token) for token in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text)]
    except ValueError as exc:
        raise OpenFOAMNativeError(f"Invalid floating-point token: {exc}") from exc
    if any(not math.isfinite(value) for value in values):
        raise OpenFOAMNativeError("Non-finite OpenFOAM coordinates or field values are not accepted.")
    return values


def _parse_points(text: str) -> list[float]:
    count, body = _counted_body(text)
    tuples = re.findall(r"\(([^()]*)\)", body)
    if len(tuples) != count:
        raise OpenFOAMNativeError(f"points declares {count} entries but {len(tuples)} were decoded.")
    values: list[float] = []
    for item in tuples:
        row = _floats(item)
        if len(row) != 3:
            raise OpenFOAMNativeError("Every OpenFOAM point must contain three coordinates.")
        values.extend(row)
    return values


def _parse_labels(text: str) -> list[int]:
    count, body = _counted_body(text)
    values = [int(token) for token in re.findall(r"[-+]?\d+", body)]
    if len(values) != count:
        raise OpenFOAMNativeError(f"label list declares {count} entries but {len(values)} were decoded.")
    if any(value < 0 for value in values):
        raise OpenFOAMNativeError("Negative mesh labels are unsupported in polyMesh connectivity.")
    return values


def _parse_faces(text: str) -> tuple[list[int], list[int]]:
    count, body = _counted_body(text)
    faces = re.findall(r"\b(\d+)\s*\(([^()]*)\)", body)
    if len(faces) != count:
        raise OpenFOAMNativeError(f"faces declares {count} entries but {len(faces)} were decoded.")
    offsets = [0]
    connectivity: list[int] = []
    for declared, raw in faces:
        labels = [int(token) for token in re.findall(r"\d+", raw)]
        if len(labels) != int(declared):
            raise OpenFOAMNativeError("A face vertex count does not match its connectivity list.")
        connectivity.extend(labels)
        offsets.append(len(connectivity))
    return offsets, connectivity


def _parse_boundary(text: str) -> list[dict[str, Any]]:
    _, body = _counted_body(text)
    patches: list[dict[str, Any]] = []
    for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_.:-]*)\s*\{(.*?)\}", body, flags=re.DOTALL):
        entries = {item.group(1): item.group(2).strip() for item in _ENTRY_RE.finditer(match.group(2))}
        patches.append(
            {
                "name": match.group(1),
                "type": entries.get("type"),
                "n_faces": int(entries["nFaces"]) if entries.get("nFaces", "").isdigit() else None,
                "start_face": int(entries["startFace"]) if entries.get("startFace", "").isdigit() else None,
                "physical_type": entries.get("physicalType"),
            }
        )
    return patches


def _parse_dimensions(text: str) -> list[float] | None:
    match = re.search(r"\bdimensions\s+\[([^\]]+)\]\s*;", text)
    if not match:
        return None
    values = _floats(match.group(1))
    if len(values) != 7:
        raise OpenFOAMNativeError("OpenFOAM dimensions must contain seven exponents.")
    return values


def _parse_uniform(raw: str, components: int) -> list[float]:
    values = _floats(raw)
    if len(values) != components:
        raise OpenFOAMNativeError(f"Uniform field requires {components} component(s); decoded {len(values)}.")
    return values


def _parse_internal_field(text: str, components: int) -> tuple[str, list[float] | None, int | None]:
    uniform = re.search(r"\binternalField\s+uniform\s+([^;]+);", text)
    if uniform:
        return "uniform", _parse_uniform(uniform.group(1), components), 1
    nonuniform = re.search(
        r"\binternalField\s+nonuniform\s+List<[^>]+>\s+(\d+)\s*\((.*?)\)\s*;",
        text,
        flags=re.DOTALL,
    )
    if not nonuniform:
        return "unsupported", None, None
    count = int(nonuniform.group(1))
    body = nonuniform.group(2)
    if components == 1:
        values = _floats(body)
    else:
        rows = re.findall(r"\(([^()]*)\)", body)
        values = []
        for row in rows:
            decoded = _floats(row)
            if len(decoded) != components:
                raise OpenFOAMNativeError("Field tuple component count does not match its class.")
            values.extend(decoded)
    if len(values) != count * components:
        raise OpenFOAMNativeError(
            f"Nonuniform field declares {count} tuples but {len(values)} scalar components were decoded."
        )
    return "nonuniform", values, count


def _bounds(points: list[float]) -> list[list[float]] | None:
    if not points:
        return None
    axes = [points[index::3] for index in range(3)]
    return [[min(axis), max(axis)] for axis in axes]


def _attempt(
    context: ExecutionContext,
    *,
    stage: str,
    outcome: AttemptOutcome,
    started_at: str,
    error: Exception | None = None,
    fallback_to: str | None = None,
    information_lost: list[str] | None = None,
    diagnostics: list[DiagnosticEvent] | None = None,
) -> None:
    context.record_attempt(
        ParserAttempt(
            attempt_id=f"attempt_{uuid.uuid4().hex[:20]}",
            stage=stage,
            backend_id="openfoam.native-ascii",
            backend_version="1.0.0",
            outcome=outcome,
            started_at=started_at,
            completed_at=utc_now_iso(),
            exception_type=type(error).__name__ if error else None,
            exception_message=str(error) if error else None,
            fallback_to=fallback_to,
            information_lost=information_lost or [],
            diagnostics=diagnostics or [],
        )
    )


def _read_text(context: ExecutionContext, path: str) -> str:
    payload = context.read_bytes(path)
    if b"\x00" in payload:
        raise OpenFOAMNativeError("Binary OpenFOAM payload detected; ASCII decoding was not attempted.")
    return payload.decode("utf-8", errors="strict")


class OpenFOAMNativeBackend:
    backend_id = "openfoam.native"
    backend_version = "1.0.0"

    def execute(self, request: InspectionExecutionRequest, context: ExecutionContext) -> dict[str, Any]:
        selected = set(request.plan.selected_paths)
        summary: dict[str, Any] = {
            "format": "OpenFOAM",
            "reader": self.backend_id,
            "mesh": {},
            "patches": [],
            "fields": [],
            "time_directories": [],
            "unsupported_directives": [],
        }

        mesh_paths = {
            "points": "constant/polyMesh/points",
            "faces": "constant/polyMesh/faces",
            "owner": "constant/polyMesh/owner",
            "neighbour": "constant/polyMesh/neighbour",
            "boundary": "constant/polyMesh/boundary",
        }
        decoded: dict[str, Any] = {}
        for kind, path in mesh_paths.items():
            if path not in selected:
                continue
            started = utc_now_iso()
            try:
                text = _read_text(context, path)
                header = _header(text)
                if header.get("format", "ascii").lower() != "ascii":
                    raise OpenFOAMNativeError("Binary OpenFOAM mesh files are not supported by the core reader.")
                if _DIRECTIVE_RE.search(text):
                    raise OpenFOAMNativeError("Executable or include directive detected in mesh input.")
                if kind == "points":
                    decoded[kind] = _parse_points(text)
                elif kind == "faces":
                    decoded["face_offsets"], decoded["face_connectivity"] = _parse_faces(text)
                elif kind in {"owner", "neighbour"}:
                    decoded[kind] = _parse_labels(text)
                else:
                    decoded[kind] = _parse_boundary(text)
                _attempt(context, stage=f"decode_{kind}", outcome=AttemptOutcome.success, started_at=started)
            except (UnicodeDecodeError, OpenFOAMNativeError, ExecutionContextError) as exc:
                diagnostic = DiagnosticEvent(
                    code="CRX-OPENFOAM-NATIVE-FALLBACK-001",
                    severity=DiagnosticSeverity.warning,
                    message=f"Native OpenFOAM {kind} decoding fell back to metadata: {exc}",
                    source_path=path,
                    parser=self.backend_id,
                    fallback_used="structured-metadata",
                    information_lost=[kind, "lazy_array"],
                )
                _attempt(
                    context,
                    stage=f"decode_{kind}",
                    outcome=AttemptOutcome.failed,
                    started_at=started,
                    error=exc,
                    fallback_to="structured-metadata",
                    information_lost=[kind, "lazy_array"],
                    diagnostics=[diagnostic],
                )

        points = decoded.get("points", [])
        if points:
            ref = context.register_numeric_array(
                points,
                dtype="float64",
                shape=(len(points) // 3, 3),
                source_asset_id="asset_openfoam_mesh",
                source_path=mesh_paths["points"],
                association="point",
                component_names=["x", "y", "z"],
                coordinate_frame_ref="openfoam_case_frame",
                backend_version=self.backend_version,
                metadata={"role": "mesh_points", "length_units": "unresolved"},
            )
            summary["mesh"]["points"] = len(points) // 3
            summary["mesh"]["points_array_id"] = ref.array_id
            summary["mesh"]["bounds"] = _bounds(points)

        for key, dtype, shape, role in (
            ("face_offsets", "int64", lambda v: (len(v),), "face_offsets"),
            ("face_connectivity", "int64", lambda v: (len(v),), "face_connectivity"),
            ("owner", "int64", lambda v: (len(v),), "owner"),
            ("neighbour", "int64", lambda v: (len(v),), "neighbour"),
        ):
            values = decoded.get(key)
            if values is None:
                continue
            ref = context.register_numeric_array(
                values,
                dtype=dtype,
                shape=shape(values),
                source_asset_id="asset_openfoam_mesh",
                source_path=mesh_paths["faces" if key.startswith("face_") else key],
                association="topology",
                backend_version=self.backend_version,
                metadata={"role": role},
            )
            summary["mesh"][f"{key}_array_id"] = ref.array_id

        offsets = decoded.get("face_offsets")
        owner = decoded.get("owner", [])
        neighbour = decoded.get("neighbour", [])
        if offsets:
            summary["mesh"]["faces"] = len(offsets) - 1
        if owner or neighbour:
            summary["mesh"]["cells"] = max([*owner, *neighbour], default=-1) + 1
            summary["mesh"]["internal_faces"] = len(neighbour)
        summary["patches"] = decoded.get("boundary", [])

        time_names = sorted(
            {
                PurePosixPath(path).parts[0]
                for path in selected
                if PurePosixPath(path).parts and _TIME_RE.match(PurePosixPath(path).parts[0])
            },
            key=lambda value: float(value),
        )
        summary["time_directories"] = time_names

        for path in sorted(selected):
            parts = PurePosixPath(path).parts
            if len(parts) != 2 or not _TIME_RE.match(parts[0]):
                continue
            started = utc_now_iso()
            try:
                text = _read_text(context, path)
                header = _header(text)
                field_class = header.get("class")
                if field_class not in _FIELD_COMPONENTS:
                    continue
                if header.get("format", "ascii").lower() != "ascii":
                    raise OpenFOAMNativeError("Binary OpenFOAM fields are not supported by the core reader.")
                directives = [line.strip() for line in _DIRECTIVE_RE.findall(text)]
                if _DIRECTIVE_RE.search(text):
                    summary["unsupported_directives"].append(path)
                    raise OpenFOAMNativeError("Include or executable directive detected; field values were not expanded.")
                components, names = _FIELD_COMPONENTS[field_class]
                dimensions = _parse_dimensions(text)
                storage, values, tuple_count = _parse_internal_field(text, components)
                field: dict[str, Any] = {
                    "name": parts[1],
                    "time": parts[0],
                    "class": field_class,
                    "components": components,
                    "dimensions": dimensions,
                    "storage": storage,
                    "tuple_count": tuple_count,
                    "array_id": None,
                }
                if values is not None:
                    shape = (tuple_count, components) if components > 1 else (tuple_count,)
                    ref = context.register_numeric_array(
                        values,
                        dtype="float64",
                        shape=shape,
                        source_asset_id="asset_openfoam_case",
                        source_path=path,
                        association="cell",
                        component_names=names,
                        time_index=parts[0],
                        backend_version=self.backend_version,
                        metadata={
                            "role": "internal_field",
                            "field_name": parts[1],
                            "field_class": field_class,
                            "dimensions": dimensions,
                            "uniform": storage == "uniform",
                        },
                    )
                    field["array_id"] = ref.array_id
                summary["fields"].append(field)
                _attempt(context, stage=f"decode_field:{path}", outcome=AttemptOutcome.success, started_at=started)
            except (UnicodeDecodeError, OpenFOAMNativeError, ExecutionContextError) as exc:
                diagnostic = DiagnosticEvent(
                    code="CRX-OPENFOAM-FIELD-FALLBACK-001",
                    severity=DiagnosticSeverity.warning,
                    message=f"OpenFOAM field {path!r} was preserved as metadata only: {exc}",
                    source_path=path,
                    parser=self.backend_id,
                    fallback_used="field-header-and-dimensions",
                    information_lost=["internal_field_values", "lazy_array"],
                )
                _attempt(
                    context,
                    stage=f"decode_field:{path}",
                    outcome=AttemptOutcome.failed,
                    started_at=started,
                    error=exc,
                    fallback_to="field-header-and-dimensions",
                    information_lost=["internal_field_values", "lazy_array"],
                    diagnostics=[diagnostic],
                )

        summary["mesh"]["complete_topology"] = all(
            key in decoded for key in ("points", "face_offsets", "face_connectivity", "owner", "neighbour", "boundary")
        )
        summary["field_count"] = len(summary["fields"])
        summary["array_count"] = len(context.arrays)
        return {"summary": summary}
