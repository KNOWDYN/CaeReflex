from typer.testing import CliRunner

from caereflex.cli.app import app

runner = CliRunner()


def test_rules_cli_lists_and_describes_pack():
    result = runner.invoke(app, ["rules", "packs", "--json"])
    assert result.exit_code == 0
    assert "openfoam.cfd-core" in result.stdout
    result = runner.invoke(app, ["rules", "describe", "openfoam.cfd-core", "--json"])
    assert result.exit_code == 0
    assert "OF-CFD-MESH-001" in result.stdout
    assert "turbulence-model" in result.stdout


def test_rules_cli_version():
    result = runner.invoke(app, ["rules", "version", "--json"])
    assert result.exit_code == 0
    assert "caereflex.physics-rule/1.0" in result.stdout
