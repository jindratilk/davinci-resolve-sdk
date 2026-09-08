"""Fusion Fuse SDK helper commands."""

from __future__ import annotations

from typing import Optional

import typer

from ..errors import handle_errors
from ..output import is_dry_run, output
from ..core import sdk_tools

app = typer.Typer(help="Fusion Fuse SDK helpers.")

examples_app = typer.Typer(help="Fuse SDK examples.")
app.add_typer(examples_app, name="examples")


@app.command("scaffold")
@handle_errors
def scaffold(
    name: str = typer.Argument(..., help="Fuse name"),
    output_path: Optional[str] = typer.Option(None, "--output", help="Output .fuse path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing Fuse file"),
):
    """Scaffold a minimal Fuse file."""
    output(sdk_tools.fuse_scaffold(name, output_path, dry_run=is_dry_run(), overwrite=overwrite), title="Fuse Scaffold")


@app.command("validate")
@handle_errors
def validate(path: str = typer.Argument(..., help=".fuse path")):
    """Validate a Fuse file."""
    output(sdk_tools.validate_fuse(path), title="Fuse Validate")


@app.command("install")
@handle_errors
def install(
    path: str = typer.Argument(..., help=".fuse path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing installed Fuse"),
):
    """Install a Fuse file into the user DaVinci Resolve support folder."""
    output(sdk_tools.install_fuse(path, dry_run=is_dry_run(), overwrite=overwrite), title="Fuse Install")


@app.command("uninstall")
@handle_errors
def uninstall(name: str = typer.Argument(..., help="Fuse name or file name")):
    """Uninstall a Fuse file."""
    output(sdk_tools.uninstall_fuse(name, dry_run=is_dry_run()), title="Fuse Uninstall")


@app.command("list")
@handle_errors
def list_fuses():
    """List installed Fuse files."""
    output(sdk_tools.list_fuses(), title="Fuses")


@examples_app.command("list")
@handle_errors
def examples_list():
    """List Fuse SDK examples."""
    output(sdk_tools.fuse_examples_list(), title="Fuse Examples")


@examples_app.command("install")
@handle_errors
def examples_install(
    name: str = typer.Argument(..., help="Fuse example file name"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing installed Fuse"),
):
    """Install a Fuse SDK example."""
    output(sdk_tools.fuse_example_install(name, dry_run=is_dry_run(), overwrite=overwrite), title="Fuse Example Install")
