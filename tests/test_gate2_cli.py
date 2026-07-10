import json
from typer.testing import CliRunner

from caereflex.cli.main import app

runner = CliRunner()


def test_existing_version_command_remains_compatible():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "1.0.0" in result.output


def test_doctor_has_machine_readable_contract_report():
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["contract_version"].startswith("2.0")
    assert payload["dependencies"]["fsspec"] is True


def test_scan_command_emits_manifest_json():
    result = runner.invoke(app, ["scan", "examples/openfoam_cavity_minimal", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "openfoam" in payload["case_hints"]
    assert payload["entries"]


def test_adapter_commands_are_exposed():
    result = runner.invoke(app, ["adapters", "list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert {item["plugin_id"] for item in payload["adapters"]} == {"gmsh", "openfoam", "vtk"}


def test_legacy_adapter_command_still_runs(tmp_path):
    result = runner.invoke(app, ["inspect-vtk", "examples/vtk_minimal/sample.vtk", "--out", str(tmp_path / "vtk.json")])
    assert result.exit_code == 0
    assert (tmp_path / "vtk.json").exists()
