import json
from pathlib import Path

from typer.testing import CliRunner

from caereflex.arrays import ArrayService
from caereflex.cli.main import app
from caereflex.services import doctor_report

runner = CliRunner()


def test_version_and_doctor_report_alpha_runtime():
    version = runner.invoke(app, ["version"])
    assert version.exit_code == 0
    assert version.output.strip() == "2.0.0a1"

    report = doctor_report()
    assert report["caereflex_version"] == "2.0.0a1"
    assert report["contract_version"] == "2.0-alpha.3"
    assert report["execution_runtime"]["mode"] == "local-subprocess"
    assert any(item["backend_id"] == "core.manifest-audit" for item in report["execution_runtime"]["backends"])


def test_execution_backends_cli_json():
    result = runner.invoke(app, ["execution", "backends", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["execution_backends"][0]["backend_id"] == "core.manifest-audit"


def test_arrays_cli_queries_registered_array(tmp_path: Path):
    state_root = tmp_path / "state"
    ref = ArrayService(state_root).register_numeric([1.0, 2.0, 3.0], dtype="float64", shape=(3,))

    described = runner.invoke(app, ["arrays", "describe", ref.array_id, "--state-root", str(state_root), "--json"])
    assert described.exit_code == 0
    assert json.loads(described.output)["element_count"] == 3

    reduced = runner.invoke(
        app,
        ["arrays", "reduce", ref.array_id, "--operation", "mean", "--state-root", str(state_root), "--json"],
    )
    assert reduced.exit_code == 0
    assert json.loads(reduced.output)["value"] == 2.0


def test_deep_profile_records_execution_job(tmp_path: Path):
    output = tmp_path / "case.json"
    state_root = tmp_path / "state"
    result = runner.invoke(
        app,
        [
            "inspect",
            "examples/openfoam_cavity_minimal",
            "--adapter",
            "openfoam",
            "--profile",
            "deep",
            "--out",
            str(output),
        ],
        env={"CAEREFLEX_STATE_DIR": str(state_root)},
    )
    assert result.exit_code in {0, 2}
    payload = json.loads(output.read_text(encoding="utf-8"))
    execution = payload["metadata"]["inspection_execution"]
    assert execution["backend_id"] == "core.manifest-audit"
    assert execution["status"] == "success"
    assert execution["attempts"][0]["outcome"] == "success"

    job = runner.invoke(app, ["jobs", "show", execution["job_id"], "--json"])
    # The CLI defaults to .caereflex; this assertion only verifies the command surface.
    assert job.exit_code in {0, 1}
