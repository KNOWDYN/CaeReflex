from __future__ import annotations

from pathlib import Path

from caereflex.contracts import CaseManifest, InspectionBudget, InspectionProfile, ManifestEntry
from caereflex.execution import execute_inspection_plan
from caereflex.plugins import get_adapter_plugin


def _execute(source: Path, filename: str, state: Path, **backend_options):
    manifest = CaseManifest(
        manifest_id=f"manifest_{filename.replace('.', '_')}",
        root_uri=source.as_uri(),
        entries=[
            ManifestEntry(
                path=filename,
                size_bytes=(source / filename).stat().st_size,
                format_hint=Path(filename).suffix.lower().lstrip("."),
                case_hint="gmsh",
            )
        ],
        detected_formats=[Path(filename).suffix.lower().lstrip(".")],
        case_hints=["gmsh"],
    )
    plan = get_adapter_plugin("gmsh").plan(
        manifest,
        InspectionProfile.deep,
        InspectionBudget(max_files=10, max_bytes_read=1024 * 1024, max_wall_time_seconds=5),
    )
    return execute_inspection_plan(
        manifest,
        plan,
        backend_id="gmsh.native",
        source_root=source,
        state_root=state,
        backend_options=backend_options,
    )


def test_cad_is_fingerprint_only_without_explicit_api_opt_in(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "model.step").write_bytes(b"ISO-10303-21;\nEND-ISO-10303-21;\n")

    result = _execute(source, "model.step", tmp_path / "state")

    assert result.status == "success"
    summary = result.metadata["backend_result"]["summary"]
    assert summary["cad_count"] == 1
    cad = summary["files"][0]
    assert cad["status"] == "fingerprinted"
    assert cad["decoded"] is False
    assert cad["kind"] == "cad_fingerprint"
    assert any(
        attempt.backend_id == "gmsh.api"
        and attempt.outcome == "skipped"
        and attempt.metadata["reason"] == "explicit_opt_in_required"
        for attempt in result.attempts
    )
    assert any(item.code == "CRX-GMSH-CAD-FINGERPRINT-001" for item in result.diagnostics)


def test_geo_never_uses_gmsh_api_even_when_api_option_is_true(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "model.geo").write_text(
        "Point(1) = {0, 0, 0, 1};\nPhysical Point(\"origin\") = {1};\n",
        encoding="utf-8",
    )

    result = _execute(source, "model.geo", tmp_path / "state", enable_gmsh_api=True)

    assert result.status == "success"
    geometry = result.metadata["backend_result"]["summary"]["files"][0]
    assert geometry["reader"] == "gmsh.geo-declaration-parser"
    assert geometry["executed"] is False
    assert not any(attempt.backend_id == "gmsh.api" for attempt in result.attempts)
