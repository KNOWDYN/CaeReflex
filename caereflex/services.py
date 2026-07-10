from __future__ import annotations
from importlib import util as importlib_util
from pathlib import Path
import platform
from typing import Any

from caereflex.contracts import CONTRACT_VERSION, CaseManifest, InspectionBudget, InspectionProfile
from caereflex.core.config import CaeReflexConfig
from caereflex.core.models import ReflexCase
from caereflex.core.errors import UnsupportedFormatError
from caereflex.adapters.gmsh import GmshAdapter
from caereflex.adapters.openfoam import OpenFOAMAdapter
from caereflex.adapters.vtk import VTKAdapter
from caereflex.discovery import CatalogStore, scan_case
from caereflex.evidence.crossref import attach_crossref as _attach_crossref, search_crossref as _search_crossref
from caereflex.exporters import (
    export_reflexcase_json, export_agent_context_json, export_agent_context_md,
    export_markdown_report, export_bibtex, load_reflexcase
)
from caereflex.plugins import adapter_capabilities, probe_manifest
from caereflex.version import __version__

EXAMPLE_NAMES = ["gmsh_minimal", "openfoam_cavity_minimal", "vtk_minimal", "crossref_context", "agent_workflow"]


def scan_path(
    path: str | Path,
    *,
    profile: InspectionProfile | str = InspectionProfile.catalog,
    budget: InspectionBudget | None = None,
    cache_path: str | Path | None = None,
    use_cache: bool = True,
) -> tuple[CaseManifest, dict[str, list[str]]]:
    manifest = scan_case(path, profile=profile, budget=budget)
    diff = {"added": [entry.path for entry in manifest.entries], "removed": [], "changed": [], "unchanged": []}
    if cache_path:
        store = CatalogStore(cache_path)
        previous = store.load(manifest.root_uri) if use_cache else None
        change = store.diff(previous, manifest)
        diff = change.model_dump(mode="json")
        if use_cache:
            store.save(manifest)
    return manifest, diff


def inspect_path(
    path: str | Path,
    adapter: str = 'auto',
    config: CaeReflexConfig | None = None,
    attach_crossref: bool = False,
    crossref_kwargs: dict[str, Any] | None = None,
    *,
    profile: InspectionProfile | str = InspectionProfile.standard,
    manifest: CaseManifest | None = None,
    discover: bool = True,
) -> ReflexCase:
    config = config or CaeReflexConfig()
    p = Path(path)
    profile = InspectionProfile(profile)
    if discover and manifest is None:
        budget = InspectionBudget(
            max_files=config.max_scan_files,
            max_depth=config.max_scan_depth,
            max_bytes_read=config.max_file_size_bytes,
        )
        manifest = scan_case(p, profile=profile, budget=budget)
    if adapter == 'auto':
        if manifest is not None:
            probes = [result for result in probe_manifest(manifest) if result.supported]
            adapter = probes[0].plugin_id if probes else detect_adapter(p)
        else:
            adapter = detect_adapter(p)
    result = inspect_with_adapter(p, adapter, config=config)
    if result.case is None:
        raise UnsupportedFormatError("No ReflexCase returned by adapter.")
    case = result.case
    case.contract_version = CONTRACT_VERSION
    case.inspection_profile = profile.value
    if manifest is not None:
        case.case_manifest = manifest.model_dump(mode="json")
        case.diagnostics = [item.model_dump(mode="json") for item in manifest.diagnostics]
        case.workspace.file_count_considered = len(manifest.entries)
        case.workspace.scan_depth = max((entry.depth for entry in manifest.entries), default=0)
        case.workspace.limits = {
            "truncated": manifest.truncated,
            "limits_reached": manifest.limits_reached,
        }
        case.metadata["adapter_probe"] = [item.model_dump(mode="json") for item in probe_manifest(manifest)]
    if attach_crossref:
        case = _attach_crossref(case, **(crossref_kwargs or {}))
    return case


def inspect_with_adapter(path: str | Path, adapter: str, config: CaeReflexConfig | None = None):
    config = config or CaeReflexConfig()
    adapters = {
        'gmsh': GmshAdapter(config), 'openfoam': OpenFOAMAdapter(config), 'vtk': VTKAdapter(config),
        'gmsh_adapter': GmshAdapter(config), 'openfoam_adapter': OpenFOAMAdapter(config), 'vtk_adapter': VTKAdapter(config),
    }
    if adapter not in adapters:
        raise UnsupportedFormatError(f"Unsupported adapter: {adapter}")
    return adapters[adapter].inspect(path)


def detect_adapter(path: Path) -> str:
    if path.is_dir():
        if (path / 'system' / 'controlDict').exists() or (path / 'constant').exists() or (path / '0').exists():
            return 'openfoam'
        suffixes = {f.suffix.lower() for f in path.rglob('*') if f.is_file()}
        if suffixes & {'.geo', '.msh', '.step', '.stp', '.iges', '.igs'}:
            return 'gmsh'
        if suffixes & {'.vtk', '.vtu', '.vtp', '.vti', '.vtr', '.vts'}:
            return 'vtk'
    suf = path.suffix.lower()
    if suf in {'.geo', '.msh', '.step', '.stp', '.iges', '.igs'}: return 'gmsh'
    if suf in {'.vtk', '.vtu', '.vtp', '.vti', '.vtr', '.vts'}: return 'vtk'
    raise UnsupportedFormatError(f"Could not detect adapter for {path}")


def doctor_report() -> dict[str, Any]:
    dependencies = {
        name: importlib_util.find_spec(module) is not None
        for name, module in {
            "pydantic": "pydantic",
            "typer": "typer",
            "rich": "rich",
            "fsspec": "fsspec",
            "meshio": "meshio",
            "gmsh": "gmsh",
            "pyvista": "pyvista",
            "vtk": "vtk",
            "fastapi": "fastapi",
            "uvicorn": "uvicorn",
        }.items()
    }
    return {
        "status": "success",
        "caereflex_version": __version__,
        "contract_version": CONTRACT_VERSION,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": dependencies,
        "adapters": [item.model_dump(mode="json") for item in adapter_capabilities()],
    }


def search_crossref(case_or_path: ReflexCase | str | Path, **kwargs: Any):
    case = load_case(case_or_path) if not isinstance(case_or_path, ReflexCase) else case_or_path
    return _search_crossref(case, **kwargs)


def attach_crossref(case_or_path: ReflexCase | str | Path, **kwargs: Any) -> ReflexCase:
    case = load_case(case_or_path) if not isinstance(case_or_path, ReflexCase) else case_or_path
    return _attach_crossref(case, **kwargs)


def export_case(case_or_path: ReflexCase | str | Path, export_type: str, out: str | Path) -> Path:
    case = load_case(case_or_path) if not isinstance(case_or_path, ReflexCase) else case_or_path
    if export_type == 'json': return export_reflexcase_json(case, out)
    if export_type == 'agent-context': return export_agent_context_json(case, out)
    if export_type == 'agent-context-md': return export_agent_context_md(case, out)
    if export_type == 'markdown': return export_markdown_report(case, out)
    if export_type == 'bibtex': return export_bibtex(case, out)
    raise ValueError(f"Unknown export type: {export_type}")


def load_case(path: str | Path) -> ReflexCase:
    return load_reflexcase(path)


def save_case(case: ReflexCase, path: str | Path) -> Path:
    return export_reflexcase_json(case, path)


def get_case_store_dir(workspace: str | Path | None = None) -> Path:
    root = Path(workspace) if workspace else Path.cwd()
    d = root / '.caereflex' / 'cases'
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_case_to_store(case: ReflexCase, workspace: str | Path | None = None) -> Path:
    return save_case(case, get_case_store_dir(workspace) / f"{case.case_id}.json")


def load_case_from_store(case_id: str, workspace: str | Path | None = None) -> ReflexCase:
    return load_case(get_case_store_dir(workspace) / f"{case_id}.json")


def list_case_store(workspace: str | Path | None = None) -> list[dict[str, Any]]:
    rows = []
    for f in sorted(get_case_store_dir(workspace).glob('case_*.json')):
        try:
            c = load_case(f)
            rows.append({"case_id": c.case_id, "case_name": c.case_name, "case_type": c.case_type, "path": str(f)})
        except Exception:
            continue
    return rows


def examples_root() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [Path.cwd() / 'examples', here.parents[1] / 'examples', here.parents[2] / 'examples']
    for c in candidates:
        if c.exists() and all((c / name).exists() for name in ['gmsh_minimal','openfoam_cavity_minimal']):
            return c
    return None


def list_examples() -> list[str]:
    root = examples_root()
    if not root:
        return []
    return [n for n in EXAMPLE_NAMES if (root / n).exists()]


def run_example(name: str, out_dir: str | Path = 'build') -> dict[str, Any]:
    root = examples_root()
    if not root:
        raise FileNotFoundError("Bundled examples were not found. Run this from the source package root or use the source zip examples/ directory.")
    if name not in EXAMPLE_NAMES:
        raise ValueError(f"Unknown example: {name}")
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    if name == 'openfoam_cavity_minimal':
        case = inspect_path(root / name, adapter='openfoam')
    elif name == 'gmsh_minimal':
        case = inspect_path(root / name / 't1.geo', adapter='gmsh')
    elif name == 'vtk_minimal':
        case = inspect_path(root / name / 'sample.vtk', adapter='vtk')
    else:
        return {"status": "success", "example": name, "message": "Context example; inspect README.md for workflow."}
    case_path = out / f"{name}.caereflex.json"
    ctx_path = out / f"{name}.agent_context.json"
    report_path = out / f"{name}.case_report.md"
    save_case(case, case_path); export_case(case, 'agent-context', ctx_path); export_case(case, 'markdown', report_path)
    return {"status": case.inspection.status.value if hasattr(case.inspection.status, "value") else str(case.inspection.status), "example": name, "case_id": case.case_id, "outputs": {"case": str(case_path), "agent_context": str(ctx_path), "report": str(report_path)}}
