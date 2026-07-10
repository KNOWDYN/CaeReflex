from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from caereflex.contracts import (
    CaseManifest,
    InspectionBudget,
    InspectionPlan,
    InspectionProfile,
    ManifestEntry,
)
from caereflex.execution import execute_inspection_plan
from caereflex.execution.compatibility import (
    FROZEN_BUILTIN_BACKENDS,
    GATE5_BACKEND_CONTRACT,
)


def _manifest(root: Path, plugin_id: str, paths: list[str]) -> CaseManifest:
    return CaseManifest(
        manifest_id=f"manifest_gate5_{plugin_id}",
        root_uri=root.as_uri(),
        entries=[
            ManifestEntry(
                path=path,
                size_bytes=(root / path).stat().st_size,
                case_hint=plugin_id,
            )
            for path in paths
        ],
        case_hints=[plugin_id],
    )


def _execute(
    tmp_path: Path,
    *,
    name: str,
    plugin_id: str,
    backend_id: str,
    files: dict[str, str],
    backend_options: dict[str, Any] | None = None,
):
    root = tmp_path / f"source-{name}"
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    paths = sorted(files)
    manifest = _manifest(root, plugin_id, paths)
    plan = InspectionPlan(
        plugin_id=plugin_id,
        profile=InspectionProfile.deep,
        selected_paths=paths,
        backend_candidates=[backend_id],
        operation=f"gate5_{name}_compatibility",
        budget=InspectionBudget(
            max_files=20,
            max_bytes_read=1024 * 1024,
            max_wall_time_seconds=15,
        ),
    )
    return execute_inspection_plan(
        manifest,
        plan,
        backend_id=backend_id,
        source_root=root,
        state_root=tmp_path / f"state-{name}",
        backend_options=backend_options,
    )


def _openfoam_points() -> str:
    return (
        "FoamFile\n{\nversion 2.0;\nformat ascii;\nclass vectorField;\nobject points;\n}\n"
        "1\n(\n(0 0 0)\n)\n"
    )


def _gmsh_triangle() -> str:
    return """$MeshFormat
2.2 0 8
$EndMeshFormat
$PhysicalNames
1
2 1 "fluid"
$EndPhysicalNames
$Nodes
3
1 0 0 0
2 1 0 0
3 0 1 0
$EndNodes
$Elements
1
1 2 2 1 1 1 2 3
$EndElements
"""


def _vtk_triangle() -> str:
    return """# vtk DataFile Version 3.0
Gate 5 compatibility fixture
ASCII
DATASET POLYDATA
POINTS 3 float
0 0 0
1 0 0
0 1 0
POLYGONS 1 4
3 0 1 2
POINT_DATA 3
SCALARS pressure float 1
LOOKUP_TABLE default
0.0 0.1 0.2
"""


def _backend_results(tmp_path: Path):
    return [
        _execute(
            tmp_path,
            name="manifest-audit",
            plugin_id="fixture",
            backend_id="core.manifest-audit",
            files={"input.dat": "metadata-only fixture\n"},
        ),
        _execute(
            tmp_path,
            name="openfoam",
            plugin_id="openfoam",
            backend_id="openfoam.native",
            files={"constant/polyMesh/points": _openfoam_points()},
        ),
        _execute(
            tmp_path,
            name="gmsh",
            plugin_id="gmsh",
            backend_id="gmsh.native",
            files={"triangle.msh": _gmsh_triangle()},
            backend_options={"disable_meshio": True},
        ),
        _execute(
            tmp_path,
            name="vtk",
            plugin_id="vtk",
            backend_id="vtk.native",
            files={"triangle.vtk": _vtk_triangle()},
            backend_options={"disable_pyvista": True, "disable_meshio": True},
        ),
    ]


def test_frozen_gate5_envelope_is_identical_across_all_built_in_backends(tmp_path: Path):
    results = _backend_results(tmp_path)
    required = {
        "contract",
        "frozen",
        "backend_id",
        "backend_version",
        "plugin_id",
        "profile",
        "read_only",
        "source_execution",
        "heavy_arrays_externalised",
        "source_paths_relative",
        "evidence_status",
        "array_count",
        "artifact_count",
        "diagnostic_count",
        "parser_attempt_count",
    }

    reports = []
    assert {result.backend_id for result in results} == set(FROZEN_BUILTIN_BACKENDS)
    for result in results:
        assert result.status == "success"
        assert result.source_mutation_detected is False
        assert result.attempts
        assert all(
            not Path(path).is_absolute() and ".." not in Path(path).parts
            for path in result.paths_accessed
        )
        summary = result.metadata["backend_result"]["summary"]
        report = summary["gate5_compatibility"]
        reports.append(report)
        assert set(report) == required
        assert report["contract"] == GATE5_BACKEND_CONTRACT
        assert report["frozen"] is True
        assert report["backend_id"] == result.backend_id
        assert report["backend_version"] == result.backend_version
        assert report["plugin_id"] == result.plugin_id
        assert report["profile"] == "deep"
        assert report["read_only"] is True
        assert report["source_execution"] is False
        assert report["heavy_arrays_externalised"] is True
        assert report["source_paths_relative"] is True
        assert report["array_count"] == len(result.arrays)
        assert report["artifact_count"] == len(result.artifacts)
        assert report["diagnostic_count"] == len(result.diagnostics)
        assert report["parser_attempt_count"] == len(result.attempts)
        json.dumps(result.model_dump(mode="json"), allow_nan=False, sort_keys=True)

    assert "metadata_only" in {report["evidence_status"] for report in reports}
    assert {"decoded", "partially_decoded"} & {report["evidence_status"] for report in reports}


def test_native_backends_externalise_arrays_with_consistent_identity(tmp_path: Path):
    results = _backend_results(tmp_path)
    native_results = [result for result in results if result.backend_id != "core.manifest-audit"]

    for result in native_results:
        assert result.arrays, result.backend_id
        artifact_uris = {artifact.uri for artifact in result.artifacts}
        for ref in result.arrays:
            assert ref.array_id
            assert ref.uri.startswith("caereflex-artifact://sha256/")
            assert ref.uri in artifact_uris
            assert ref.source_path and not Path(ref.source_path).is_absolute()
            assert ".." not in Path(ref.source_path).parts
            assert ref.backend == result.backend_id
            assert ref.permitted_operations


def test_gate5_compatibility_envelope_is_additive_to_backend_specific_summaries(tmp_path: Path):
    results = {result.backend_id: result for result in _backend_results(tmp_path)}

    assert "entries" in results["core.manifest-audit"].metadata["backend_result"]["summary"]
    assert "mesh" in results["openfoam.native"].metadata["backend_result"]["summary"]
    assert "files" in results["gmsh.native"].metadata["backend_result"]["summary"]
    assert "files" in results["vtk.native"].metadata["backend_result"]["summary"]
