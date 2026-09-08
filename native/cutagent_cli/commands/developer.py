"""DaVinci Resolve Developer SDK documentation and diagnostics."""

from __future__ import annotations

from typing import Optional

import typer

from ..errors import handle_errors
from ..output import is_dry_run, output
from ..core import sdk_tools

app = typer.Typer(help="DaVinci Resolve Developer SDK docs, examples, and diagnostics.")

docs_app = typer.Typer(help="Local DaVinci Resolve Developer documentation.")
app.add_typer(docs_app, name="docs")

examples_app = typer.Typer(help="Local DaVinci Resolve Developer examples.")
app.add_typer(examples_app, name="examples")

capability_app = typer.Typer(help="CLI capability audit helpers.")
app.add_typer(capability_app, name="capability")
sdk_app = typer.Typer(help="DaVinci Resolve Developer SDK diagnostics.")
app.add_typer(sdk_app, name="sdk")


@docs_app.command("list")
@handle_errors
def docs_list():
    """List known local DaVinci Resolve Developer documentation files."""
    output(sdk_tools.list_developer_docs(), title="Developer Docs")


@docs_app.command("open")
@handle_errors
def docs_open(
    section: str = typer.Argument(..., help="scripting|workflow|dctl|lut|fusion-template|fuse|openfx|codec"),
):
    """Open a local DaVinci Resolve Developer documentation section."""
    output(sdk_tools.open_developer_doc(section, dry_run=is_dry_run()), title="Developer Docs")


@examples_app.command("list")
@handle_errors
def examples_list(
    section: Optional[str] = typer.Option(None, "--section", help="Optional SDK section"),
):
    """List local DaVinci Resolve Developer examples."""
    output(sdk_tools.list_examples(section), title="Developer Examples")


@examples_app.command("copy")
@handle_errors
def examples_copy(
    section: str = typer.Argument(..., help="SDK section"),
    name: str = typer.Argument(..., help="Example file name or relative path"),
    dest: str = typer.Argument(..., help="Destination path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing destination"),
):
    """Copy a local DaVinci Resolve Developer example."""
    output(sdk_tools.copy_example(section, name, dest, dry_run=is_dry_run(), overwrite=overwrite), title="Developer Example Copy")


@app.command("sdk-doctor")
@app.command("doctor")
@sdk_app.command("doctor")
@handle_errors
def sdk_doctor():
    """Inspect local DaVinci Resolve Developer SDK availability."""
    output(sdk_tools.sdk_doctor(), title="Developer SDK Doctor")


@capability_app.command("audit")
@handle_errors
def capability_audit():
    """Audit command/capability parity."""
    output(sdk_tools.capability_audit(), title="Capability Audit")


@capability_app.command("diff")
@handle_errors
def capability_diff():
    """Show compact command/capability diff."""
    output(sdk_tools.capability_diff(), title="Capability Diff")
