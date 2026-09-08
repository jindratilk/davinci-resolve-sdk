"""Burn-in preset commands."""

from __future__ import annotations

import typer

from ..connection import get_connection
from ..errors import handle_errors
from ..output import dry_run_message, is_dry_run, output
from ..policy import enforce_mutation_policy
from ..core import render_engine

app = typer.Typer(help="Burn-in preset operations.")

preset_app = typer.Typer(help="Burn-in preset import/export operations.")
app.add_typer(preset_app, name="preset")


@preset_app.command("import")
@handle_errors
def preset_import(
    path: str = typer.Argument(..., help="Burn-in preset file path"),
):
    """Import a burn-in preset."""
    enforce_mutation_policy("render.burnin_preset_import_export", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would import burn-in preset from: {path}")
        return
    conn = get_connection(require_project=False)
    output(render_engine.import_burnin_preset(conn, path), title="Burn-In Preset Import")


@preset_app.command("export")
@handle_errors
def preset_export(
    name: str = typer.Argument(..., help="Burn-in preset name"),
    path: str = typer.Argument(..., help="Export path"),
):
    """Export a burn-in preset."""
    enforce_mutation_policy("render.burnin_preset_import_export", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would export burn-in preset '{name}' to: {path}")
        return
    conn = get_connection(require_project=False)
    output(render_engine.export_burnin_preset(conn, name, path), title="Burn-In Preset Export")


@app.command("load")
@handle_errors
def load(
    name: str = typer.Argument(..., help="Burn-in preset name"),
):
    """Load a burn-in preset."""
    enforce_mutation_policy("render.burnin_preset_import_export", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would load burn-in preset: {name}")
        return
    conn = get_connection(require_project=True)
    output(render_engine.load_burnin_preset(conn, name), title="Burn-In Preset Load")
