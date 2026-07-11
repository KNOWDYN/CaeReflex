"""Composed CaeReflex CLI application.

The legacy command module remains import-compatible while this composition layer adds
spatial and deterministic physics-rule command groups without duplicating commands.
"""
from caereflex.cli.main import app
from caereflex.cli.rules import rules_app
from caereflex.cli.spatial import spatial_app

app.add_typer(spatial_app, name="spatial")
app.add_typer(rules_app, name="rules")

__all__ = ["app"]
