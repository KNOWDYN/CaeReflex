"""Adapter plugin discovery and built-in capability declarations."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from pathlib import PurePosixPath
import re
from typing import Iterable

from caereflex.contracts import (
    AdapterCapabilities,
    AdapterPlugin,
    CaseManifest,
    DiagnosticEvent,
    DiagnosticSeverity,
    InspectionBudget,
    InspectionPlan,
    InspectionProfile,
    ProbeResult,
)

PLUGIN_GROUP = "caereflex.adapters"
_TIME_RE = re.compile(r"^(?:0|[1-9]\d*)(?:\.\d+)?$")


@dataclass(frozen=True)
class BuiltinAdapterPlugin:
    plugin_id: str
    plugin_version: str
    _capabilities: AdapterCapabilities
    format_hints: frozenset[str]
    case_hints: frozenset[str]

    def capabilities(self) -> AdapterCapabilities:
        return self._capabilities

    def probe(self, manifest: CaseManifest) -> ProbeResult:
        formats = set(manifest.detected_formats)
        cases = set(manifest.case_hints)
        format_hits = sorted(formats & set(self.format_hints))
        case_hits = sorted(cases & set(self.case_hints))
        supported = bool(format_hits or case_hits)
        score = min(1.0, 0.55 * len(format_hits) + 0.65 * len(case_hits)) if supported else 0.0
        reasons = [f"format:{item}" for item in format_hits] + [f"case:{item}" for item in case_hits]
        return ProbeResult(plugin_id=self.plugin_id, supported=supported, score=score, reasons=reasons)

    def plan(
        self,
        manifest: CaseManifest,
        profile: InspectionProfile,
        budget: InspectionBudget,
    ) -> InspectionPlan:
        if self.plugin_id == "openfoam":
            paths: list[str] = []
            for entry in manifest.entries:
                if entry.is_dir:
                    continue
                parts = PurePosixPath(entry.path).parts
                if not parts:
                    continue
                first = parts[0]
                if first in {"system", "constant"} or _TIME_RE.match(first):
                    paths.append(entry.path)
            paths = paths[: budget.max_files]
            return InspectionPlan(
                plugin_id=self.plugin_id,
                profile=profile,
                selected_paths=paths,
                budget=budget,
                backend_candidates=["openfoam.native", "core.manifest-audit"],
                operation="native_openfoam_inspection",
                metadata={"reader_policy": "ascii-native-with-metadata-fallback"},
            )
        paths = [
            entry.path
            for entry in manifest.entries
            if entry.format_hint in self.format_hints or entry.case_hint in self.case_hints
        ]
        return InspectionPlan(plugin_id=self.plugin_id, profile=profile, selected_paths=paths, budget=budget)


_BUILTINS: tuple[BuiltinAdapterPlugin, ...] = (
    BuiltinAdapterPlugin(
        plugin_id="gmsh",
        plugin_version="1.0.0",
        _capabilities=AdapterCapabilities(
            plugin_id="gmsh",
            plugin_version="1.0.0",
            formats=["gmsh-geo", "gmsh-msh", "step-detected", "iges-detected"],
            geometry_support="declaration-summary",
            topology_support="optional-meshio-summary",
            field_support="none",
            units_support="none",
            fallback_modes=["text-summary", "fingerprint-only"],
            optional_dependencies=["meshio", "gmsh"],
            licence="CaeReflex core; optional backend licences vary",
        ),
        format_hints=frozenset({"gmsh-geo", "gmsh-msh", "step", "iges"}),
        case_hints=frozenset({"gmsh"}),
    ),
    BuiltinAdapterPlugin(
        plugin_id="openfoam",
        plugin_version="1.2.0",
        _capabilities=AdapterCapabilities(
            plugin_id="openfoam",
            plugin_version="1.2.0",
            formats=["openfoam-case", "openfoam-polyMesh", "openfoam-field"],
            geometry_support="native-ascii-points-and-bounds",
            topology_support="native-ascii-faces-owner-neighbour-boundary",
            field_support="native-ascii-uniform-and-nonuniform-internal-fields",
            time_series_support=True,
            units_support="seven-component-dimension-vector-and-Pint-validation",
            fallback_modes=[
                "field-header-and-dimensions",
                "structured-metadata",
                "raw-text-with-diagnostic",
                "fingerprint-only",
            ],
            optional_dependencies=[],
            licence="CaeReflex Research Source Licence; Pint is BSD-licensed core dependency",
        ),
        format_hints=frozenset({"openfoam-case", "openfoam-dictionary", "openfoam-field"}),
        case_hints=frozenset({"openfoam"}),
    ),
    BuiltinAdapterPlugin(
        plugin_id="vtk",
        plugin_version="1.0.0",
        _capabilities=AdapterCapabilities(
            plugin_id="vtk",
            plugin_version="1.0.0",
            formats=["vtk-legacy", "vtk-xml", "vtk-collection"],
            geometry_support="dataset-bounds-planned",
            topology_support="legacy-header-summary",
            field_support="legacy-scalar-vector-summary",
            time_series_support=False,
            units_support="metadata-only",
            fallback_modes=["legacy-header", "fingerprint-only"],
            optional_dependencies=["pyvista", "vtk", "meshio"],
            licence="CaeReflex core; optional backend licences vary",
        ),
        format_hints=frozenset({"vtk-legacy", "vtk-xml", "vtk-collection"}),
        case_hints=frozenset({"vtk"}),
    ),
)


def builtin_plugins() -> list[BuiltinAdapterPlugin]:
    return list(_BUILTINS)


def external_plugins() -> list[AdapterPlugin]:
    plugins: list[AdapterPlugin] = []
    try:
        entry_points = metadata.entry_points()
        selected = entry_points.select(group=PLUGIN_GROUP) if hasattr(entry_points, "select") else entry_points.get(PLUGIN_GROUP, [])
    except Exception:
        return plugins
    for entry_point in selected:
        try:
            loaded = entry_point.load()
            plugin = loaded() if isinstance(loaded, type) else loaded
            if isinstance(plugin, AdapterPlugin):
                plugins.append(plugin)
        except Exception:
            continue
    return plugins


def iter_adapter_plugins(include_external: bool = True) -> Iterable[AdapterPlugin]:
    yield from _BUILTINS
    if include_external:
        yield from external_plugins()


def adapter_capabilities(include_external: bool = True) -> list[AdapterCapabilities]:
    return [plugin.capabilities() for plugin in iter_adapter_plugins(include_external=include_external)]


def get_adapter_plugin(plugin_id: str, include_external: bool = True) -> AdapterPlugin | None:
    target = plugin_id.lower()
    for plugin in iter_adapter_plugins(include_external=include_external):
        if plugin.plugin_id.lower() == target:
            return plugin
    return None


def probe_manifest(manifest: CaseManifest, include_external: bool = True) -> list[ProbeResult]:
    results = [plugin.probe(manifest) for plugin in iter_adapter_plugins(include_external=include_external)]
    results.sort(key=lambda item: (-item.score, item.plugin_id))
    if not any(result.supported for result in results):
        results.append(
            ProbeResult(
                plugin_id="none",
                supported=False,
                score=0.0,
                diagnostics=[
                    DiagnosticEvent(
                        code="CRX-PLUGIN-NONE-001",
                        severity=DiagnosticSeverity.warning,
                        message="No installed adapter matched the case manifest.",
                    )
                ],
            )
        )
    return results
