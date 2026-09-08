"""LUT helper commands."""

from __future__ import annotations

import typer

from ..errors import handle_errors
from ..output import is_dry_run, output
from ..core import sdk_tools

app = typer.Typer(help="LUT validation, installation, listing, and generation.")

generate_app = typer.Typer(help="LUT generation helpers.")
app.add_typer(generate_app, name="generate")


@app.command("validate")
@handle_errors
def validate(path: str = typer.Argument(..., help=".cube path")):
    """Validate a LUT file."""
    output(sdk_tools.validate_lut(path), title="LUT Validate")


@app.command("inspect")
@handle_errors
def inspect(path: str = typer.Argument(..., help=".cube path")):
    """Inspect a LUT file."""
    output(sdk_tools.inspect_lut(path), title="LUT Inspect")


@app.command("install")
@handle_errors
def install(
    path: str = typer.Argument(..., help="LUT path"),
    folder: str | None = typer.Option(None, "--folder", help="User LUT subfolder"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing installed LUT"),
):
    """Install a LUT into the user DaVinci Resolve LUT folder."""
    output(sdk_tools.install_lut(path, folder, dry_run=is_dry_run(), overwrite=overwrite), title="LUT Install")


@app.command("list")
@handle_errors
def list_luts(
    resolve: bool = typer.Option(False, "--resolve", help="Include system/DaVinci Resolve SDK LUT roots"),
):
    """List LUT files."""
    output(sdk_tools.list_luts(resolve), title="LUT Files")


@app.command("remove")
@handle_errors
def remove(name: str = typer.Argument(..., help="LUT file name or relative path")):
    """Remove a user-installed LUT."""
    output(sdk_tools.remove_lut(name, dry_run=is_dry_run()), title="LUT Remove")


@generate_app.command("identity")
@handle_errors
def generate_identity(
    size: int = typer.Option(..., "--size", help="Cube size"),
    output_path: str = typer.Option(..., "--output", help="Output .cube path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing output file"),
):
    """Generate an identity .cube LUT."""
    output(sdk_tools.generate_identity_lut(size, output_path, dry_run=is_dry_run(), overwrite=overwrite), title="LUT Generate")


@app.command("convert")
@handle_errors
def convert(
    path: str = typer.Argument(..., help="Source LUT path"),
    fmt: str = typer.Option(..., "--format", help="Target format, currently cube"),
):
    """Convert or validate LUT format support."""
    output(sdk_tools.convert_lut(path, fmt), title="LUT Convert")
