"""OpenFX SDK helper commands."""

from __future__ import annotations

from typing import Optional

import typer

from ..errors import handle_errors
from ..output import is_dry_run, output
from ..core import sdk_tools

app = typer.Typer(help="OpenFX SDK scaffold, build, package, and install helpers.")

sample_app = typer.Typer(help="OpenFX SDK samples.")
app.add_typer(sample_app, name="sample")


@app.command("scaffold")
@handle_errors
def scaffold(
    kind: str = typer.Argument(..., help="filter|transition"),
    name: str = typer.Argument(..., help="Plugin name"),
    output_path: Optional[str] = typer.Option(None, "--output", help="Output folder"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace existing generated scaffold files"),
):
    """Scaffold a minimal OpenFX plugin project."""
    output(sdk_tools.ofx_scaffold(kind, name, output_path, dry_run=is_dry_run(), overwrite=overwrite), title="OpenFX Scaffold")


@app.command("build")
@handle_errors
def build(
    path: str = typer.Argument(..., help="Project folder"),
    backend: Optional[str] = typer.Option(None, "--backend", help="cpu|cuda|opencl|metal"),
):
    """Build an OpenFX project with make when available."""
    output(sdk_tools.build_with_make(path, backend=backend, dry_run=is_dry_run()), title="OpenFX Build")


@app.command("install")
@handle_errors
def install(
    path_or_bundle: str = typer.Argument(..., help="OpenFX bundle/path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing installed bundle"),
):
    """Install an OpenFX bundle into the user OFX folder."""
    output(sdk_tools.ofx_install(path_or_bundle, dry_run=is_dry_run(), overwrite=overwrite), title="OpenFX Install")


@app.command("uninstall")
@handle_errors
def uninstall(plugin_id: str = typer.Argument(..., help="Plugin ID/folder name")):
    """Uninstall a user OpenFX bundle."""
    output(sdk_tools.ofx_uninstall(plugin_id, dry_run=is_dry_run()), title="OpenFX Uninstall")


@app.command("list-installed")
@handle_errors
def list_installed():
    """List user-installed OpenFX bundles."""
    output(sdk_tools.ofx_list_installed(), title="OpenFX Installed")


@app.command("validate")
@handle_errors
def validate(path_or_bundle: str = typer.Argument(..., help="OpenFX project/bundle path")):
    """Validate that an OpenFX path or bundle exists."""
    output(sdk_tools.validate_bundle(path_or_bundle, (".bundle", ".ofx")), title="OpenFX Validate")


@app.command("package")
@handle_errors
def package(
    path: str = typer.Argument(..., help="Project/bundle path"),
    output_bundle: str = typer.Option(..., "--output", help="Output bundle/zip path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing package file"),
):
    """Package an OpenFX project or bundle."""
    output(sdk_tools.ofx_package(path, output_bundle, dry_run=is_dry_run(), overwrite=overwrite), title="OpenFX Package")


@sample_app.command("copy")
@handle_errors
def sample_copy(
    name: str = typer.Argument(..., help="Sample name or relative path"),
    dest: str = typer.Argument(..., help="Destination path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing destination"),
):
    """Copy an OpenFX SDK sample."""
    output(sdk_tools.ofx_sample_copy(name, dest, dry_run=is_dry_run(), overwrite=overwrite), title="OpenFX Sample Copy")
