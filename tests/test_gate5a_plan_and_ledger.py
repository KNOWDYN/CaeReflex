from pathlib import Path

import pytest

from caereflex.contracts import CaseManifest, InspectionBudget, InspectionPlan, InspectionProfile, ManifestEntry
from caereflex.execution import InspectionExecutionError, execute_inspection_plan


def _fixture(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "input.dat").write_bytes(b"fixture")
    manifest = CaseManifest(
        manifest_id="manifest_plan_fixture",
        root_uri=source.as_uri(),
        entries=[ManifestEntry(path="input.dat", size_bytes=7)],
    )
    plan = InspectionPlan(
        plugin_id="fixture",
        profile=InspectionProfile.deep,
        selected_paths=["input.dat"],
        backend_candidates=["test.execution"],
        budget=InspectionBudget(max_files=10, max_wall_time_seconds=5.0),
    )
    return source, manifest, plan


def test_backend_must_be_declared_by_plan(tmp_path: Path):
    source, manifest, plan = _fixture(tmp_path)
    with pytest.raises(InspectionExecutionError, match="backend_candidates"):
        execute_inspection_plan(
            manifest,
            plan,
            backend_id="core.manifest-audit",
            source_root=source,
            state_root=tmp_path / "state",
        )


def test_selected_path_must_exist_in_manifest(tmp_path: Path):
    source, manifest, plan = _fixture(tmp_path)
    plan.selected_paths = ["not-in-manifest.dat"]
    with pytest.raises(InspectionExecutionError, match="absent from the case manifest"):
        execute_inspection_plan(
            manifest,
            plan,
            backend_id="test.execution",
            source_root=source,
            state_root=tmp_path / "state",
        )


def test_backend_can_record_ordered_fallback_attempts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CAEREFLEX_ENABLE_TEST_BACKENDS", "1")
    source, manifest, plan = _fixture(tmp_path)
    result = execute_inspection_plan(
        manifest,
        plan,
        backend_id="test.execution",
        source_root=source,
        state_root=tmp_path / "state",
        backend_options={"mode": "fallback"},
    )

    assert result.status == "success"
    assert [attempt.backend_id for attempt in result.attempts] == ["test.native", "test.structured"]
    assert [attempt.outcome for attempt in result.attempts] == ["failed", "success"]
    assert result.attempts[0].fallback_to == "test.structured"
    assert result.attempts[0].information_lost == ["native_topology"]
    assert result.metadata["backend_result"]["summary"]["fallback_used"] == "test.structured"
