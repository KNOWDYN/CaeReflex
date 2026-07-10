from pathlib import Path

from caereflex.contracts import CaseManifest, InspectionBudget, InspectionPlan, InspectionProfile, ManifestEntry
from caereflex.core.models import ReflexCase
from caereflex.execution import execute_inspection_plan
from caereflex.version import __version__


def test_new_reflexcase_is_stamped_with_current_package_version():
    case = ReflexCase(case_id="case_version_fixture")
    assert case.caereflex_version == __version__ == "2.0.0a1"


def test_single_file_source_root_is_normalized_to_parent(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CAEREFLEX_ENABLE_TEST_BACKENDS", "1")
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_file = source_dir / "sample.vtk"
    source_file.write_bytes(b"vtk-fixture")

    manifest = CaseManifest(
        manifest_id="manifest_single_file",
        root_uri=source_file.as_uri(),
        entries=[ManifestEntry(path=source_file.name, size_bytes=source_file.stat().st_size)],
        detected_formats=["vtk-legacy"],
        case_hints=["vtk"],
    )
    plan = InspectionPlan(
        plugin_id="vtk",
        profile=InspectionProfile.deep,
        selected_paths=[source_file.name],
        backend_candidates=["test.execution"],
        budget=InspectionBudget(max_bytes_read=1024, max_wall_time_seconds=5.0),
    )

    result = execute_inspection_plan(
        manifest,
        plan,
        backend_id="test.execution",
        source_root=source_file,
        state_root=tmp_path / "state",
        backend_options={"mode": "read", "path": source_file.name, "length": 4},
    )

    assert result.status == "success"
    assert result.paths_accessed == [source_file.name]
    assert result.bytes_read == 4
