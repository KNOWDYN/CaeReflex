from pathlib import Path

from caereflex.arrays import ArrayService
from caereflex.contracts import (
    CaseManifest,
    ExecutionPolicy,
    InspectionBudget,
    InspectionPlan,
    InspectionProfile,
    ManifestEntry,
)
from caereflex.execution import execute_inspection_plan
from caereflex.jobs import JobStore


def _manifest(source_root: Path) -> CaseManifest:
    return CaseManifest(
        manifest_id="manifest_gate5a_fixture",
        root_uri=source_root.as_uri(),
        entries=[ManifestEntry(path="input.dat", size_bytes=(source_root / "input.dat").stat().st_size)],
        detected_formats=["fixture"],
        case_hints=["fixture"],
    )


def _plan(wall_time: float = 5.0) -> InspectionPlan:
    return InspectionPlan(
        plugin_id="fixture",
        profile=InspectionProfile.deep,
        selected_paths=["input.dat"],
        backend_candidates=["test.execution"],
        budget=InspectionBudget(
            max_files=10,
            max_depth=2,
            max_bytes_read=1024,
            max_wall_time_seconds=wall_time,
            max_array_elements_returned=100,
        ),
    )


def _source(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "input.dat").write_bytes(b"unchanged-source")
    return source_root


def test_execution_registers_array_and_preserves_source(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CAEREFLEX_ENABLE_TEST_BACKENDS", "1")
    source_root = _source(tmp_path)
    original = (source_root / "input.dat").read_bytes()
    state_root = tmp_path / "state"

    result = execute_inspection_plan(
        _manifest(source_root),
        _plan(),
        backend_id="test.execution",
        source_root=source_root,
        state_root=state_root,
        backend_options={
            "mode": "emit_array",
            "values": [1.0, 2.0, 3.0, 4.0],
            "shape": [2, 2],
            "dtype": "float64",
            "component_names": ["x", "y"],
        },
        policy=ExecutionPolicy(max_memory_bytes=512 * 1024 * 1024),
    )

    assert result.status == "success"
    assert result.source_mutation_detected is False
    assert (source_root / "input.dat").read_bytes() == original
    assert len(result.attempts) == 1
    assert result.attempts[0].outcome == "success"
    assert len(result.arrays) == 1
    assert len(result.artifacts) == 1

    array_id = result.arrays[0].array_id
    arrays = ArrayService(state_root)
    assert arrays.reduce(array_id, "sum")["value"] == 10.0

    job = JobStore(state_root).get(result.job_id)
    assert job.status == "success"
    assert job.result_summary["array_count"] == 1


def test_execution_read_budget_and_relative_path_ledger(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CAEREFLEX_ENABLE_TEST_BACKENDS", "1")
    source_root = _source(tmp_path)
    result = execute_inspection_plan(
        _manifest(source_root),
        _plan(),
        backend_id="test.execution",
        source_root=source_root,
        state_root=tmp_path / "state",
        backend_options={"mode": "read", "path": "input.dat", "length": 8},
    )
    assert result.status == "success"
    assert result.bytes_read == 8
    assert result.paths_accessed == ["input.dat"]


def test_execution_timeout_isolated_from_parent(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CAEREFLEX_ENABLE_TEST_BACKENDS", "1")
    source_root = _source(tmp_path)
    result = execute_inspection_plan(
        _manifest(source_root),
        _plan(wall_time=0.2),
        backend_id="test.execution",
        source_root=source_root,
        state_root=tmp_path / "state",
        backend_options={"mode": "sleep", "seconds": 2.0},
    )
    assert result.status == "timed_out"
    assert result.diagnostics[0].code == "CRX-EXEC-TIMEOUT-001"
    assert result.attempts[0].outcome == "timed_out"


def test_execution_crash_becomes_diagnostic(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CAEREFLEX_ENABLE_TEST_BACKENDS", "1")
    source_root = _source(tmp_path)
    result = execute_inspection_plan(
        _manifest(source_root),
        _plan(),
        backend_id="test.execution",
        source_root=source_root,
        state_root=tmp_path / "state",
        backend_options={"mode": "crash", "exit_code": 23},
    )
    assert result.status == "crashed"
    assert result.worker_exit_code == 23
    assert result.diagnostics[0].code == "CRX-EXEC-CRASH-001"


def test_backend_exception_returns_failed_attempt(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CAEREFLEX_ENABLE_TEST_BACKENDS", "1")
    source_root = _source(tmp_path)
    result = execute_inspection_plan(
        _manifest(source_root),
        _plan(),
        backend_id="test.execution",
        source_root=source_root,
        state_root=tmp_path / "state",
        backend_options={"mode": "fail", "message": "fixture failure"},
    )
    assert result.status == "failed"
    assert result.attempts[0].outcome == "failed"
    assert result.diagnostics[0].code == "CRX-EXEC-BACKEND-001"
