"""Composed CaeReflex CLI application.

The legacy command module remains import-compatible while this composition layer adds the
Gate 6 spatial command group without duplicating existing command definitions.
"""
from caereflex.cli.main import app
from caereflex.cli.spatial import spatial_app

app.add_typer(spatial_app, name="spatial")

__all__ = ["app"]
