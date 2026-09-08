"""DCTL helper commands."""

from __future__ import annotations

from typing import Optional

import typer

from ..connection import get_connection
from ..errors import ValidationError, handle_errors
from ..output import dry_run_message, is_dry_run, output
from ..policy import enforce_mutation_policy
from ..core import color_ops, sdk_tools

app = typer.Typer(help="DCTL validation, installation, and application helpers.")


@app.command("validate")
@handle_errors
def validate(
    path: str = typer.Argument(..., help=".dctl path"),
):
    """Validate a DCTL source file with lightweight static checks."""
    output(sdk_tools.validate_dctl(path), title="DCTL Validate")


@app.command("scaffold")
@handle_errors
def scaffold(
    kind: str = typer.Argument(..., help="transform|transition|aces-idt|aces-odt"),
    name: str = typer.Argument(..., help="DCTL name"),
    output_path: Optional[str] = typer.Option(None, "--output", help="Output .dctl path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing scaffold file"),
):
    """Scaffold a minimal DCTL file."""
    output(sdk_tools.scaffold_dctl(kind, name, output_path, dry_run=is_dry_run(), overwrite=overwrite), title="DCTL Scaffold")


@app.command("install")
@handle_errors
def install(
    path: str = typer.Argument(..., help=".dctl path"),
    kind: str = typer.Option("lut", "--kind", help="lut|aces-idt|aces-odt"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing installed DCTL"),
):
    """Install a DCTL into a user DaVinci Resolve support folder."""
    output(sdk_tools.install_dctl(path, kind, dry_run=is_dry_run(), overwrite=overwrite), title="DCTL Install")


@app.command("list")
@handle_errors
def list_dctl():
    """List DCTL files in user/SDK folders."""
    output(sdk_tools.list_dctl(), title="DCTL Files")


@app.command("apply")
@handle_errors
def apply(
    clip: str = typer.Argument(..., help="Timeline clip name"),
    name: str = typer.Argument(..., help="DCTL/LUT name or path"),
    node: int = typer.Option(1, "--node", help="Color node index"),
):
    """Apply a DCTL as a node LUT to a timeline clip."""
    clip = str(clip or "").strip()
    name = str(name or "").strip()
    if not clip:
        raise ValidationError("DCTL apply clip name must not be empty.", details={"clip": clip})
    if not name:
        raise ValidationError("DCTL apply name/path must not be empty.", details={"name": name})
    if node < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"node": node, "minimum": 1},
            recoverability="not_applicable",
        )
    enforce_mutation_policy("color.lut_set_clear", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would apply DCTL/LUT '{name}' to node {node} on clip '{clip}'.")
        return
    conn = get_connection(require_timeline=True)
    color_ops.set_lut(conn, clip, node, name)
    readback = color_ops.get_lut_info(conn, clip, node)
    output(
        {
            "clip": clip,
            "node": node,
            "applied": True,
            "requested_dctl": name,
            "readback": readback,
            "readback_lut_path": readback.get("lut_path"),
            "route": "api_native_dctl_apply",
            "alias_of": "color lut --set",
        },
        title="DCTL Apply",
    )
