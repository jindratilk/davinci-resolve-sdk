"""Codec Plugin SDK helper commands."""

from __future__ import annotations

from typing import Optional

import typer

from ..errors import handle_errors
from ..output import is_dry_run, output
from ..core import sdk_tools

app = typer.Typer(help="Codec Plugin SDK scaffold, build, package, and install helpers.")

sample_app = typer.Typer(help="Codec SDK samples.")
app.add_typer(sample_app, name="sample")


@app.command("scaffold")
@handle_errors
def scaffold(
    kind: str = typer.Argument(..., help="encoder"),
    name: str = typer.Argument(..., help="Plugin name"),
    output_path: Optional[str] = typer.Option(None, "--output", help="Output folder"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace existing generated scaffold files"),
):
    """Scaffold a minimal codec plugin project."""
    output(sdk_tools.codec_scaffold(kind, name, output_path, dry_run=is_dry_run(), overwrite=overwrite), title="Codec Scaffold")


@app.command("build")
@handle_errors
def build(path: str = typer.Argument(..., help="Project folder")):
    """Build a codec plugin project with make when available."""
    output(sdk_tools.build_with_make(path, dry_run=is_dry_run()), title="Codec Build")


@app.command("package")
@handle_errors
def package(
    path: str = typer.Argument(..., help="Project/bundle path"),
    arch: str = typer.Option(..., "--arch", help="MacOS|MacOS-x86-64|Linux-x86-64|Win64"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing package file"),
):
    """Package a codec plugin project for an architecture label."""
    output(sdk_tools.codec_package(path, arch, dry_run=is_dry_run(), overwrite=overwrite), title="Codec Package")


@app.command("install")
@handle_errors
def install(
    bundle: str = typer.Argument(..., help="Plugin bundle/path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing installed bundle"),
):
    """Install a codec plugin bundle."""
    output(sdk_tools.codec_install(bundle, dry_run=is_dry_run(), overwrite=overwrite), title="Codec Install")


@app.command("uninstall")
@handle_errors
def uninstall(name: str = typer.Argument(..., help="Plugin name/folder")):
    """Uninstall a codec plugin bundle."""
    output(sdk_tools.codec_uninstall(name, dry_run=is_dry_run()), title="Codec Uninstall")


@app.command("list-installed")
@handle_errors
def list_installed():
    """List user-installed codec plugin bundles."""
    output(sdk_tools.codec_list_installed(), title="Codec Installed")


@app.command("validate")
@handle_errors
def validate(bundle: str = typer.Argument(..., help="Plugin bundle/path")):
    """Validate that a codec plugin bundle exists."""
    output(sdk_tools.validate_bundle(bundle, (".bundle", ".plugin", ".dylib")), title="Codec Validate")


@sample_app.command("copy")
@handle_errors
def sample_copy(
    name: str = typer.Argument(..., help="Sample name or relative path"),
    dest: str = typer.Argument(..., help="Destination path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing destination"),
):
    """Copy a codec SDK sample."""
    output(sdk_tools.codec_sample_copy(name, dest, dry_run=is_dry_run(), overwrite=overwrite), title="Codec Sample Copy")
