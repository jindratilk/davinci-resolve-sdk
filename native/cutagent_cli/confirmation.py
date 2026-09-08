"""Confirmation helpers for destructive CLI operations."""

from __future__ import annotations

from typing import Any

import typer

from .errors import ConfirmationRequired
from .output import is_machine_mode


def require_force_for_machine_mode(
    *,
    force: bool,
    action: str,
    target_kind: str,
    target_name: Any,
    prompt: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Require --force for live destructive operations in machine mode."""
    if force:
        return

    payload = {
        "action": action,
        "target_kind": target_kind,
        "target_name": target_name,
        "required_option": "--force",
    }
    if details:
        payload.update(details)

    if is_machine_mode():
        raise ConfirmationRequired(
            "Machine-mode mutation requires --force.",
            details=payload,
        )

    if prompt:
        typer.confirm(prompt, abort=True)
