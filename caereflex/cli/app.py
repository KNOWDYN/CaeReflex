"""Composed CaeReflex CLI application."""
from caereflex.cli.main import app
from caereflex.cli.physics import physics_app
from caereflex.cli.spatial import spatial_app

app.add_typer(spatial_app, name="spatial")
app.add_typer(physics_app, name="physics")

__all__ = ["app"]
