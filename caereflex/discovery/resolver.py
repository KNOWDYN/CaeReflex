"""Bounded, read-only case discovery for local and fsspec-backed storage."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path, PurePosixPath
from typing import Iterable

import fsspec

from caereflex.contracts import (
    CaseManifest,
    DiagnosticEvent,
    DiagnosticSeverity,
    InspectionBudget,
    InspectionProfile,
    ManifestEntry,
    ManifestRole,
)

_GEOMETRY_SUFFIXES = {".geo", ".step", ".stp", ".iges", ".igs", ".brep"}
_MESH_SUFFIXES = {".msh", ".med", ".mesh", ".cgns", ".exo", ".e", ".neu"}
_VTK_LEGACY_SUFFIXES = {".vtk"}
_VTK_XML_SUFFIXES = {".vtu", ".vtp", ".vti", ".vtr", ".vts", ".pvtu", ".pvtp", ".pvti", ".pvtr", ".pvts"}
_VTK_COLLECTION_SUFFIXES = {".pvd", ".vtm", ".vtmb"}
_LITERATURE_SUFFIXES = {".bib", ".ris", ".enw"}
_TIME_DIR_RE = re.compile(r"^(?:\d+(?:\.\d+)?|constant)$")


def _normalise_uri(uri: str | Path) -> str:
    return str(uri).replace("\\", "/")


def _role_for(path: str, is_dir: bool) -> tuple[ManifestRole, str | None, str | None]:
    pure = PurePosixPath(path)
    name = pure.name
    suffix = pure.suffix.lower()
    parts = pure.parts

    if is_dir:
        if name.startswith("processor") and name[9:].isdigit():
            return ManifestRole.directory, None, "openfoam"
        if _TIME_DIR_RE.match(name):
            return ManifestRole.directory, None, "openfoam"
        return ManifestRole.directory, None, None

    lower_path = path.lower()
    if suffix == ".geo":
        return ManifestRole.geometry, "gmsh-geo", "gmsh"
    if suffix == ".msh":
        return ManifestRole.mesh, "gmsh-msh", "gmsh"
    if suffix in {".step", ".stp"}:
        return ManifestRole.geometry, "step", "gmsh"
    if suffix in {".iges", ".igs"}:
        return ManifestRole.geometry, "iges", "gmsh"
    if suffix in _GEOMETRY_SUFFIXES:
        return ManifestRole.geometry, suffix.lstrip("."), None
    if suffix in _MESH_SUFFIXES:
        return ManifestRole.mesh, suffix.lstrip("."), None
    if suffix in _VTK_LEGACY_SUFFIXES:
        return ManifestRole.result, "vtk-legacy", "vtk"
    if suffix in _VTK_XML_SUFFIXES:
        return ManifestRole.result, "vtk-xml", "vtk"
    if suffix in _VTK_COLLECTION_SUFFIXES:
        return ManifestRole.result, "vtk-collection", "vtk"
    if suffix in _LITERATURE_SUFFIXES:
        return ManifestRole.literature, suffix.lstrip("."), None

    if lower_path.endswith("system/controldict"):
        return ManifestRole.solver_control, "openfoam-case", "openfoam"
    if any(lower_path.endswith(f"system/{item}") for item in ("fvschemes", "fvsolution", "decomposepardict")):
        return ManifestRole.solver_dictionary, "openfoam-dictionary", "openfoam"
    if "/constant/" in f"/{lower_path}" or lower_path.startswith("constant/"):
        if "/polymesh/" in f"/{lower_path}":
            return ManifestRole.mesh, "openfoam-case", "openfoam"
        return ManifestRole.solver_dictionary, "openfoam-dictionary", "openfoam"
    if parts and parts[0] == "0":
        return ManifestRole.initial_field, "openfoam-field", "openfoam"
    if parts and _TIME_DIR_RE.match(parts[0]) and parts[0] not in {"0", "constant"}:
        return ManifestRole.time_field, "openfoam-field", "openfoam"
    if name == "log" or name.startswith("log.") or suffix in {".log", ".out", ".err"}:
        return ManifestRole.log, None, None
    return ManifestRole.unknown, None, None


def _manifest_signature(root_uri: str, entries: Iterable[ManifestEntry]) -> str:
    rows = [
        (entry.path, entry.is_dir, entry.size_bytes, entry.modified_ns, entry.role, entry.format_hint, entry.case_hint)
        for entry in entries
    ]
    payload = json.dumps([root_uri, rows], sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _manifest_id(root_uri: str, signature: str) -> str:
    return "manifest_" + hashlib.sha1(f"{root_uri}:{signature}".encode("utf-8")).hexdigest()[:16]


def _limit_event(code: str, message: str, limit: str) -> DiagnosticEvent:
    return DiagnosticEvent(
        code=code,
        severity=DiagnosticSeverity.warning,
        message=message,
        details={"limit": limit},
    )


def _scan_local(root: Path, budget: InspectionBudget) -> tuple[list[ManifestEntry], list[str], list[DiagnosticEvent]]:
    started = time.monotonic()
    entries: list[ManifestEntry] = []
    limits_reached: list[str] = []
    diagnostics: list[DiagnosticEvent] = []
    stack: list[tuple[Path, int]] = [(root, 0)]

    while stack:
        if time.monotonic() - started > budget.max_wall_time_seconds:
            limits_reached.append("max_wall_time_seconds")
            diagnostics.append(_limit_event("CRX-SCAN-LIMIT-003", "Catalog wall-time limit reached.", "max_wall_time_seconds"))
            break
        current, depth = stack.pop()
        try:
            with os.scandir(current) as iterator:
                children = sorted(list(iterator), key=lambda item: item.name.lower(), reverse=True)
        except OSError as exc:
            diagnostics.append(
                DiagnosticEvent(
                    code="CRX-SCAN-READ-001",
                    severity=DiagnosticSeverity.warning,
                    message=f"Directory could not be catalogued: {current.name}",
                    source_path=str(current),
                    details={"error": type(exc).__name__},
                )
            )
            continue

        for child in children:
            if len(entries) >= budget.max_files:
                limits_reached.append("max_files")
                diagnostics.append(_limit_event("CRX-SCAN-LIMIT-001", "Catalog file-count limit reached.", "max_files"))
                stack.clear()
                break
            try:
                is_symlink = child.is_symlink()
                is_dir = child.is_dir(follow_symlinks=False)
                stat = child.stat(follow_symlinks=False)
            except OSError:
                continue
            rel = Path(child.path).relative_to(root).as_posix()
            role, format_hint, case_hint = _role_for(rel, is_dir)
            entry = ManifestEntry(
                path=rel,
                is_dir=is_dir,
                role=role,
                suffix=Path(child.name).suffix.lower() or None,
                size_bytes=None if is_dir else stat.st_size,
                modified_ns=getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
                depth=depth + 1,
                format_hint=format_hint,
                case_hint=case_hint,
                metadata={"symlink": is_symlink} if is_symlink else {},
            )
            entries.append(entry)
            if is_symlink:
                diagnostics.append(
                    DiagnosticEvent(
                        code="CRX-SCAN-SYMLINK-001",
                        severity=DiagnosticSeverity.info,
                        message="Symbolic link catalogued but not followed.",
                        source_path=rel,
                    )
                )
                continue
            if is_dir:
                if depth + 1 >= budget.max_depth:
                    limits_reached.append("max_depth")
                    diagnostics.append(
                        _limit_event("CRX-SCAN-LIMIT-002", f"Depth limit prevented traversal of {rel}.", "max_depth")
                    )
                else:
                    stack.append((Path(child.path), depth + 1))
    return entries, sorted(set(limits_reached)), diagnostics


def _scan_fsspec(uri: str, budget: InspectionBudget) -> tuple[str, str, list[ManifestEntry], list[str], list[DiagnosticEvent]]:
    fs, fs_path = fsspec.core.url_to_fs(uri)
    protocol = fs.protocol[0] if isinstance(fs.protocol, (tuple, list)) else str(fs.protocol)
    started = time.monotonic()
    entries: list[ManifestEntry] = []
    limits_reached: list[str] = []
    diagnostics: list[DiagnosticEvent] = []

    if protocol in {"file", "local"}:
        local_root = Path(fs_path).resolve()
        if local_root.is_file():
            stat = local_root.stat()
            role, format_hint, case_hint = _role_for(local_root.name, False)
            entries.append(
                ManifestEntry(
                    path=local_root.name,
                    role=role,
                    suffix=local_root.suffix.lower() or None,
                    size_bytes=stat.st_size,
                    modified_ns=stat.st_mtime_ns,
                    depth=0,
                    format_hint=format_hint,
                    case_hint=case_hint,
                )
            )
            return local_root.as_posix(), "file", entries, limits_reached, diagnostics
        if not local_root.exists():
            raise FileNotFoundError(f"Case root does not exist: {uri}")
        entries, limits_reached, diagnostics = _scan_local(local_root, budget)
        return local_root.as_posix(), "file", entries, limits_reached, diagnostics

    if not fs.exists(fs_path):
        raise FileNotFoundError(f"Case root does not exist: {uri}")
    root_parts = PurePosixPath(fs_path).parts
    for dirpath, dirs, files in fs.walk(fs_path, maxdepth=budget.max_depth):
        if time.monotonic() - started > budget.max_wall_time_seconds:
            limits_reached.append("max_wall_time_seconds")
            diagnostics.append(_limit_event("CRX-SCAN-LIMIT-003", "Catalog wall-time limit reached.", "max_wall_time_seconds"))
            break
        depth = max(0, len(PurePosixPath(dirpath).parts) - len(root_parts))
        names = [(name, True) for name in dirs] + [(name, False) for name in files]
        for name, is_dir in sorted(names):
            if len(entries) >= budget.max_files:
                limits_reached.append("max_files")
                diagnostics.append(_limit_event("CRX-SCAN-LIMIT-001", "Catalog file-count limit reached.", "max_files"))
                break
            full = f"{dirpath.rstrip('/')}/{name}"
            rel = PurePosixPath(full).relative_to(PurePosixPath(fs_path)).as_posix()
            info = fs.info(full)
            role, format_hint, case_hint = _role_for(rel, is_dir)
            modified = info.get("mtime") or info.get("LastModified")
            modified_ns = int(modified.timestamp() * 1_000_000_000) if hasattr(modified, "timestamp") else None
            entries.append(
                ManifestEntry(
                    path=rel,
                    is_dir=is_dir,
                    role=role,
                    suffix=PurePosixPath(name).suffix.lower() or None,
                    size_bytes=None if is_dir else info.get("size"),
                    modified_ns=modified_ns,
                    depth=depth + 1,
                    format_hint=format_hint,
                    case_hint=case_hint,
                )
            )
        if "max_files" in limits_reached:
            break
    return _normalise_uri(uri), protocol, entries, sorted(set(limits_reached)), diagnostics


def scan_case(
    uri: str | Path,
    *,
    profile: InspectionProfile | str = InspectionProfile.catalog,
    budget: InspectionBudget | None = None,
) -> CaseManifest:
    """Create a bounded metadata manifest without reading CAE payload arrays."""
    budget = budget or InspectionBudget()
    profile = InspectionProfile(profile)
    root_uri, protocol, entries, limits_reached, diagnostics = _scan_fsspec(_normalise_uri(uri), budget)
    detected_formats = sorted({entry.format_hint for entry in entries if entry.format_hint})
    case_hints = sorted({entry.case_hint for entry in entries if entry.case_hint})
    bytes_catalogued = sum(entry.size_bytes or 0 for entry in entries if not entry.is_dir)
    signature = _manifest_signature(root_uri, entries)
    return CaseManifest(
        manifest_id=_manifest_id(root_uri, signature),
        root_uri=root_uri,
        storage_protocol=protocol,
        profile=profile,
        entries=sorted(entries, key=lambda entry: entry.path),
        detected_formats=detected_formats,
        case_hints=case_hints,
        bytes_catalogued=bytes_catalogued,
        truncated=bool(limits_reached),
        limits_reached=limits_reached,
        diagnostics=diagnostics,
        signature=signature,
    )
