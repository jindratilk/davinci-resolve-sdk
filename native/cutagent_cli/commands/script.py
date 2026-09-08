"""DaVinci Resolve script helper commands."""

from __future__ import annotations

from typing import Optional

import typer

from ..errors import handle_errors
from ..output import is_dry_run, output
from ..core import sdk_tools

app = typer.Typer(help="DaVinci Resolve scripting environment and install helpers.")

env_app = typer.Typer(help="DaVinci Resolve scripting environment.")
app.add_typer(env_app, name="env")


@env_app.command("print")
@handle_errors
def env_print():
    """Print DaVinci Resolve scripting environment diagnostics."""
    output(sdk_tools.script_env(), title="Script Environment")


@app.command("list")
@handle_errors
def list_scripts():
    """List installed DaVinci Resolve scripts."""
    output(sdk_tools.list_scripts(), title="DaVinci Resolve Scripts")


@app.command("install")
@handle_errors
def install(
    path: str = typer.Argument(..., help="Script path"),
    page: str = typer.Option("Utility", "--page", help="Utility|Edit|Color|Deliver|Fusion"),
    name: Optional[str] = typer.Option(None, "--name", help="Installed file name"),
    all_users: bool = typer.Option(False, "--all-users", help="Install into the system support folder"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing installed script"),
):
    """Install a DaVinci Resolve script into a page folder."""
    output(
        sdk_tools.install_script(path, page=page, name=name, all_users=all_users, dry_run=is_dry_run(), overwrite=overwrite),
        title="Script Install",
    )


@app.command("uninstall")
@handle_errors
def uninstall(
    name: str = typer.Argument(..., help="Installed script file name"),
    page: str = typer.Option(..., "--page", help="Utility|Edit|Color|Deliver|Fusion"),
    all_users: bool = typer.Option(False, "--all-users", help="Remove from the system support folder"),
):
    """Uninstall a DaVinci Resolve script."""
    output(sdk_tools.uninstall_script(name, page=page, all_users=all_users, dry_run=is_dry_run()), title="Script Uninstall")


@app.command("run")
@handle_errors
def run(
    path: str = typer.Argument(..., help="Script path"),
    args: Optional[list[str]] = typer.Option(None, "--args", help="Argument to pass; repeat for multiple values"),
):
    """Run a local helper script outside DaVinci Resolve."""
    output(sdk_tools.run_script(path, args or [], dry_run=is_dry_run()), title="Script Run")
