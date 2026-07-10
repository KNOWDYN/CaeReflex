import json

from typer.testing import CliRunner

from caereflex.cli.main import app
from caereflex.contracts import CONTRACT_VERSION

runner = CliRunner()


def test_units_parse_json_handles_offset_temperature():
    result = runner.invoke(app, ["units", "parse", "25 degC", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert abs(payload["normalized_magnitude"] - 298.15) < 1e-10
    assert payload["dimension_vector"] == [0, 0, 0, 1, 0, 0, 0]


def test_units_convert_json():
    result = runner.invoke(app, ["units", "convert", "1", "bar", "Pa", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["output_magnitude"] == 100000.0
    assert payload["dimension_vector"] == [1, -1, -2, 0, 0, 0, 0]


def test_units_check_compatible():
    result = runner.invoke(app, ["units", "check", "m/s", "velocity", "--name", "U", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "consistent"
    assert payload["blocks_automated_interpretation"] is False


def test_units_check_conflict_uses_review_exit_code():
    result = runner.invoke(app, ["units", "check", "Pa", "velocity", "--name", "U", "--json"])
    assert result.exit_code == 6
    payload = json.loads(result.output)
    assert payload["status"] == "conflicted"
    assert payload["diagnostic_code"] == "CRX-UNITS-DIMENSION-MISMATCH-001"
    assert payload["blocks_automated_interpretation"] is True


def test_doctor_reports_pint_backend():
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["dependencies"]["pint"] is True
    assert payload["units_backend"] == "Pint"
    assert payload["contract_version"] == CONTRACT_VERSION
