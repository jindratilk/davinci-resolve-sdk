"""Workflow Integration SDK helper commands."""

from __future__ import annotations

from typing import Optional

import typer

from ..errors import ValidationError, handle_errors
from ..output import is_dry_run, output
from ..core import sdk_tools

app = typer.Typer(help="DaVinci Resolve Workflow Integration SDK helpers.")

plugin_app = typer.Typer(help="Workflow plugin helpers.")
app.add_typer(plugin_app, name="plugin")

node_app = typer.Typer(help="Workflow Node.js helpers.")
app.add_typer(node_app, name="node")

callback_app = typer.Typer(help="Workflow callback script helpers.")
app.add_typer(callback_app, name="callback")
callback_script_app = typer.Typer(help="Workflow callback script creation.")
callback_app.add_typer(callback_script_app, name="script")

script_app = typer.Typer(help="Workflow script install helpers.")
app.add_typer(script_app, name="script")

ui_app = typer.Typer(help="Workflow UI scaffolding.")
app.add_typer(ui_app, name="ui")


def _all_users(user: bool, all_users: bool) -> bool:
    if user and all_users:
        raise ValidationError("Use either --user or --all-users, not both.")
    return all_users


@plugin_app.command("scaffold")
@handle_errors
def plugin_scaffold(
    plugin_id: str = typer.Argument(..., help="Plugin ID"),
    name: str = typer.Option(..., "--name", help="Plugin display name"),
    output_path: Optional[str] = typer.Option(None, "--output", help="Output folder"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace existing generated scaffold files"),
):
    """Scaffold a minimal workflow plugin."""
    output(
        sdk_tools.workflow_plugin_scaffold(plugin_id, name, output_path, dry_run=is_dry_run(), overwrite=overwrite),
        title="Workflow Plugin Scaffold",
    )


@plugin_app.command("validate")
@handle_errors
def plugin_validate(path: str = typer.Argument(..., help="Plugin folder path")):
    """Validate a workflow plugin folder."""
    output(sdk_tools.validate_workflow_plugin(path), title="Workflow Plugin Validate")


@plugin_app.command("install")
@handle_errors
def plugin_install(
    path: str = typer.Argument(..., help="Plugin folder path"),
    user: bool = typer.Option(False, "--user", help="Install into the user folder"),
    all_users: bool = typer.Option(False, "--all-users", help="Install into the system folder"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing installed plugin"),
):
    """Install a workflow plugin."""
    output(
        sdk_tools.install_workflow_plugin(path, all_users=_all_users(user, all_users), dry_run=is_dry_run(), overwrite=overwrite),
        title="Workflow Plugin Install",
    )


@plugin_app.command("uninstall")
@handle_errors
def plugin_uninstall(
    plugin_id: str = typer.Argument(..., help="Plugin folder/ID"),
    user: bool = typer.Option(False, "--user", help="Remove from the user folder"),
    all_users: bool = typer.Option(False, "--all-users", help="Remove from the system folder"),
):
    """Uninstall a workflow plugin."""
    output(
        sdk_tools.uninstall_workflow_plugin(plugin_id, all_users=_all_users(user, all_users), dry_run=is_dry_run()),
        title="Workflow Plugin Uninstall",
    )


@plugin_app.command("list")
@handle_errors
def plugin_list():
    """List installed workflow plugins."""
    output(sdk_tools.list_workflow_plugins(), title="Workflow Plugins")


@plugin_app.command("info")
@handle_errors
def plugin_info(path: str = typer.Argument(..., help="Plugin folder path")):
    """Show workflow plugin manifest info."""
    output(sdk_tools.workflow_plugin_info(path), title="Workflow Plugin Info")


@plugin_app.command("package")
@handle_errors
def plugin_package(
    path: str = typer.Argument(..., help="Plugin folder path"),
    output_zip: str = typer.Option(..., "--output", help="Output zip path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing package file"),
):
    """Package a workflow plugin folder."""
    output(sdk_tools.package_path(path, output_zip, dry_run=is_dry_run(), overwrite=overwrite), title="Workflow Plugin Package")


@node_app.command("check")
@handle_errors
def node_check(path: str = typer.Argument(..., help="JavaScript file path")):
    """Run node --check when Node.js is available."""
    output(sdk_tools.node_check(path, dry_run=is_dry_run()), title="Workflow Node Check")


@callback_script_app.command("create")
@handle_errors
def callback_script_create(
    kind: str = typer.Argument(..., help="render-start|render-stop|resolve-quit"),
    output_path: str = typer.Option(..., "--output", help="Output script path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing script"),
):
    """Create a workflow callback script stub."""
    output(sdk_tools.create_callback_script(kind, output_path, dry_run=is_dry_run(), overwrite=overwrite), title="Workflow Callback Script")


@script_app.command("install")
@handle_errors
def script_install(
    path: str = typer.Argument(..., help="Script path"),
    name: Optional[str] = typer.Option(None, "--name", help="Installed file name"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing installed script"),
):
    """Install a workflow helper script into DaVinci Resolve's Utility scripts."""
    output(sdk_tools.install_script(path, page="Utility", name=name, dry_run=is_dry_run(), overwrite=overwrite), title="Workflow Script Install")


@ui_app.command("scaffold")
@handle_errors
def ui_scaffold(
    python: bool = typer.Option(False, "--python", help="Create a Python script"),
    lua: bool = typer.Option(False, "--lua", help="Create a Lua script"),
    name: str = typer.Option(..., "--name", help="UI script name"),
    output_path: Optional[str] = typer.Option(None, "--output", help="Output folder"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace existing generated scaffold files"),
):
    """Scaffold a minimal workflow UI script."""
    if python and lua:
        raise ValidationError("Use either --python or --lua, not both.")
    language = "lua" if lua else "python"
    output(sdk_tools.workflow_ui_scaffold(language, name, output_path, dry_run=is_dry_run(), overwrite=overwrite), title="Workflow UI Scaffold")
