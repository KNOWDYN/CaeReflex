from __future__ import annotations

from pathlib import Path

import pytest

from caereflex.contracts import CaseManifest, InspectionBudget, InspectionProfile, ManifestEntry
from caereflex.execution import execute_inspection_plan
from caereflex.plugins import get_adapter_plugin


@pytest.mark.optional_gmsh
def test_explicit_gmsh_api_inspects_brep_without_mesh_generation(tmp_path: Path):
    gmsh = pytest.importorskip("gmsh")

    source = tmp_path / "source"
    source.mkdir()
    brep_path = source / "box.brep"

    gmsh.initialize(["caereflex-test", "-nopopup"])
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("box")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 1.0, 2.0, 3.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(brep_path))
    finally:
        gmsh.finalize()

    manifest = CaseManifest(
        manifest_id="manifest_gmsh_api_optional",
        root_uri=source.as_uri(),
        entries=[
            ManifestEntry(
                path=brep_path.name,
                size_bytes=brep_path.stat().st_size,
                format_hint="brep",
                case_hint="gmsh",
            )
        ],
        detected_formats=["brep"],
        case_hints=["gmsh"],
    )
    plan = get_adapter_plugin("gmsh").plan(
        manifest,
        InspectionProfile.deep,
        InspectionBudget(max_files=10, max_bytes_read=5 * 1024 * 1024, max_wall_time_seconds=20),
    )

    result = execute_inspection_plan(
        manifest,
        plan,
        backend_id="gmsh.native",
        source_root=source,
        state_root=tmp_path / "state",
        backend_options={"enable_gmsh_api": True},
    )

    assert result.status == "success"
    model = result.metadata["backend_result"]["summary"]["files"][0]
    assert model["reader"] == "gmsh-api"
    assert model["mesh_generation_requested"] is False
    assert model["entity_count"] > 0
    assert model["dimension"] == 3
    assert model["node_count"] == 0
    assert model["element_count"] == 0
    assert result.source_mutation_detected is False
    assert any(attempt.backend_id == "gmsh.api" and attempt.outcome == "success" for attempt in result.attempts)
