from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from caereflex.cli.app import app
from caereflex.contracts import InspectionProfile
from caereflex.core.config import CaeReflexConfig
from caereflex.services import inspect_path
from caereflex.spatial import SpatialStore

runner = CliRunner()


def _deep_graph(tmp_path: Path) -> tuple[Path, str, str]:
    source = Path(__file__).resolve().parents[1] / "examples" / "openfoam_cavity_native"
    state = tmp_path / "state"
    case = inspect_path(
        source,
        adapter="openfoam",
        profile=InspectionProfile.deep,
        config=CaeReflexConfig(state_dir=state),
    )
    graph_id = case.metadata["spatial_graph_refs"][0]["graph_id"]
    graph = SpatialStore(state).get_graph(graph_id)
    assert graph.default_coordinate_frame_id is not None
    return state, graph_id, graph.default_coordinate_frame_id


def test_spatial_cli_lists_queries_and_validates_graph(tmp_path: Path) -> None:
    state, graph_id, frame_id = _deep_graph(tmp_path)

    version = runner.invoke(app, ["spatial", "version", "--json"])
    assert version.exit_code == 0, version.output
    assert "caereflex.spatial-query/1.0" in version.output

    show = runner.invoke(
        app,
        ["spatial", "show", graph_id, "--state-root", str(state), "--json"],
    )
    assert show.exit_code == 0, show.output
    show_payload = json.loads(show.output)
    assert show_payload["graph_id"] == graph_id
    assert show_payload["metadata"]["heavy_arrays_materialized"] is False

    entities = runner.invoke(
        app,
        [
            "spatial",
            "entities",
            graph_id,
            "--kinds",
            "patch,mesh_cell",
            "--state-root",
            str(state),
            "--json",
        ],
    )
    assert entities.exit_code == 0, entities.output
    assert json.loads(entities.output)["entities"]

    bounds = runner.invoke(
        app,
        [
            "spatial",
            "bounds",
            graph_id,
            "--frame-id",
            frame_id,
            "--minimum",
            "0,0,0",
            "--maximum",
            "1,1,1",
            "--state-root",
            str(state),
            "--json",
        ],
    )
    assert bounds.exit_code == 0, bounds.output
    bounds_payload = json.loads(bounds.output)
    assert bounds_payload["metadata"]["coordinate_transforms_applied"] is False

    validation = runner.invoke(
        app,
        ["spatial", "validate", graph_id, "--state-root", str(state), "--json"],
    )
    assert validation.exit_code == 0, validation.output
    assert json.loads(validation.output)["accepted"] is True


def test_spatial_cli_rejects_unknown_graph(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "spatial",
            "show",
            "graph_missing",
            "--state-root",
            str(tmp_path / "state"),
            "--json",
        ],
    )
    assert result.exit_code == 1
    assert "Unknown spatial graph" in result.output
