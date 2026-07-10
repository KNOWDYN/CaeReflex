from typer.testing import CliRunner

from caereflex.cli.main import app
from caereflex.version import __version__

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == __version__


def test_examples_list():
    result = runner.invoke(app, ["examples", "list"])
    assert result.exit_code == 0
    assert "openfoam_cavity_minimal" in result.output
