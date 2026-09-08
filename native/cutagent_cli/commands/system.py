"""System-level DaVinci Resolve commands."""

from __future__ import annotations

import typer

from ..connection import get_connection
from ..errors import ValidationError, handle_errors
from ..output import dry_run_message, is_dry_run, output
from ..policy import enforce_mutation_policy
from ..core import clip_ops

app = typer.Typer(help="DaVinci Resolve system-level operations.")

keyframe_mode_app = typer.Typer(help="DaVinci Resolve keyframe mode.")
app.add_typer(keyframe_mode_app, name="keyframe-mode")


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
