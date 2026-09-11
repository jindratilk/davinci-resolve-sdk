"""System-level DaVinci Resolve commands."""

from __future__ import annotations

import typer

from ..connection import get_connection
from ..errors import ConfirmationRequired, ValidationError, handle_errors
from ..output import dry_run_message, is_dry_run, is_machine_mode, mutation_payload, output, set_capability_context
from ..policy import enforce_mutation_policy
from ..core import clip_ops, keyboard_preset_api

app = typer.Typer(help="DaVinci Resolve system-level operations.")

keyframe_mode_app = typer.Typer(help="DaVinci Resolve keyframe mode.")
app.add_typer(keyframe_mode_app, name="keyframe-mode")
keyboard_preset_app = typer.Typer(help="DaVinci Resolve keyboard preset operations.")
app.add_typer(keyboard_preset_app, name="keyboard-preset")


@keyboard_preset_app.command("list")
@handle_errors
def keyboard_preset_list():
    """List available keyboard presets."""
    enforce_mutation_policy(
        "system.keyboard_preset.list", intended_engine="api_native", mutating=False
    )
    set_capability_context("system.keyboard_preset_read", "supported")
    conn = get_connection(require_project=False)
    output(
        {"presetNames": keyboard_preset_api.list_keyboard_presets(conn)},
        title="Keyboard Presets",
    )


@keyboard_preset_app.command("current")
@handle_errors
def keyboard_preset_current():
    """Get the currently active keyboard preset."""
    enforce_mutation_policy(
        "system.keyboard_preset.current", intended_engine="api_native", mutating=False
    )
    set_capability_context("system.keyboard_preset_read", "supported")
    conn = get_connection(require_project=False)
    output(
        {"presetName": keyboard_preset_api.get_current_keyboard_preset(conn)},
        title="Current Keyboard Preset",
    )


@keyboard_preset_app.command("load")
@handle_errors
def keyboard_preset_load(name: str = typer.Argument(..., help="Exact preset name")):
    """Load an exact keyboard preset."""
    keyboard_preset_api.requested_preset_name(name)
    enforce_mutation_policy("system.keyboard_preset.load", intended_engine="api_native", mutating=not is_dry_run())
    set_capability_context("system.keyboard_preset_management", "supported")
    if is_dry_run():
        output(mutation_payload(action="system.keyboard_preset.load", target={"kind": "keyboard_preset", "name": name}, changed=False))
        return
    conn = get_connection(require_project=False)
    output(keyboard_preset_api.load_keyboard_preset(conn, name), title="Keyboard Preset Load")


@keyboard_preset_app.command("delete")
@handle_errors
def keyboard_preset_delete(
    name: str = typer.Argument(..., help="Exact preset name"),
    force: bool = typer.Option(False, "--force", "-f", help="Confirm deletion"),
):
    """Delete one inactive keyboard preset."""
    keyboard_preset_api.requested_preset_name(name)
    enforce_mutation_policy("system.keyboard_preset.delete", intended_engine="api_native", mutating=not is_dry_run())
    set_capability_context("system.keyboard_preset_management", "supported")
    if is_dry_run():
        output(mutation_payload(action="system.keyboard_preset.delete", target={"kind": "keyboard_preset", "name": name}, changed=False))
        return
    if not force:
        if is_machine_mode():
            raise ConfirmationRequired("Machine-mode deletion requires --force.", details={"preset_name": name})
        if not typer.confirm(f"Delete keyboard preset {name!r}?"):
            raise typer.Abort()
    conn = get_connection(require_project=False)
    output(keyboard_preset_api.delete_keyboard_preset(conn, name), title="Keyboard Preset Delete")


@keyboard_preset_app.command("import")
@handle_errors
def keyboard_preset_import(
    path: str = typer.Argument(..., help="Keyboard preset file path"),
    name: str | None = typer.Option(None, "--name", help="Exact imported preset name"),
):
    """Import a keyboard preset from one local file."""
    enforce_mutation_policy("system.keyboard_preset.import", intended_engine="api_native", mutating=not is_dry_run())
    set_capability_context("system.keyboard_preset_management", "supported")
    if is_dry_run():
        if name is not None:
            keyboard_preset_api.requested_preset_name(name)
        output(mutation_payload(action="system.keyboard_preset.import", target={"kind": "keyboard_preset", "name": name}, changed=False, path=path))
        return
    conn = get_connection(require_project=False)
    output(keyboard_preset_api.import_keyboard_preset(conn, path, name), title="Keyboard Preset Import")


@keyboard_preset_app.command("export")
@handle_errors
def keyboard_preset_export(
    name: str = typer.Argument(..., help="Exact preset name"),
    path: str = typer.Argument(..., help="New export file path"),
):
    """Export one keyboard preset without replacing a file."""
    keyboard_preset_api.requested_preset_name(name)
    enforce_mutation_policy("system.keyboard_preset.export", intended_engine="api_native", mutating=not is_dry_run())
    set_capability_context("system.keyboard_preset_management", "supported")
    if is_dry_run():
        output(mutation_payload(action="system.keyboard_preset.export", target={"kind": "keyboard_preset", "name": name}, changed=False, path=path))
        return
    conn = get_connection(require_project=False)
    output(keyboard_preset_api.export_keyboard_preset(conn, name, path), title="Keyboard Preset Export")


@keyframe_mode_app.command("get")
@handle_errors
def keyframe_mode_get():
    """Get the current keyframe mode."""
    conn = get_connection(require_project=False)
    output(clip_ops.get_keyframe_mode(conn), title="Keyframe Mode")


@keyframe_mode_app.command("set")
@handle_errors
def keyframe_mode_set(
    mode: str = typer.Argument(..., help="all|color|sizing"),
):
    """Set the current keyframe mode."""
    if mode not in {"all", "color", "sizing"}:
        raise ValidationError("Invalid keyframe mode. Use all, color, or sizing.", details={"mode": mode})
    enforce_mutation_policy("system.keyframe_mode", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would set keyframe mode to: {mode}")
        return
    conn = get_connection(require_project=False)
    data = clip_ops.set_keyframe_mode(conn, {"all": 0, "color": 1, "sizing": 2}[mode])
    data["mode_name"] = mode
    output(data, title="Keyframe Mode")
