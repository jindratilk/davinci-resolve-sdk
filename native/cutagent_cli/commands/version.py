"""Prompt checkpoint and version history commands."""

from __future__ import annotations

import re
from typing import Optional

import typer

from ..connection import get_connection
from ..errors import ValidationError, handle_errors
from ..output import is_dry_run, mutation_payload, output, set_recoverability, set_verification_status
from ..policy import enforce_mutation_policy
from ..core import version_ops
from . import utility


app = typer.Typer(
    help="Prompt checkpoints and version history.",
    invoke_without_command=True,
)


def _checkpoint_dry_run_payload(*, label: str, kind: str, session_id: str | None, prompt_event_id: str | None) -> dict[str, object]:
    return mutation_payload(
        action="version.create",
        changed=False,
        target={"kind": "checkpoint", "label": label, "checkpoint_kind": kind},
        session_id=session_id,
        prompt_event_id=prompt_event_id,
        restore_strategy=version_ops.RESTORE_STRATEGY,
        message="DRY-RUN: Would save the active DaVinci Resolve project and store a compressed Project.db snapshot.",
    )


@app.callback(invoke_without_command=True)
def version_root(ctx: typer.Context):
    """Show CLI/DaVinci Resolve version when no checkpoint subcommand is supplied."""
    if ctx.invoked_subcommand is not None:
        return
    utility.version()


@app.command("create")
@handle_errors
def create(
    label: str = typer.Option("", "--label", help="Human label for this checkpoint"),
    kind: str = typer.Option("manual_commit", "--kind", help="Checkpoint kind: before_prompt|after_prompt|manual_commit"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="CutAgent session id"),
    prompt_event_id: Optional[str] = typer.Option(None, "--prompt-event-id", help="CutAgent prompt event id"),
    parent_checkpoint_id: Optional[str] = typer.Option(None, "--parent-id", help="Optional parent checkpoint id"),
):
    """Create a project checkpoint from the active DaVinci Resolve Disk Project.db."""
    enforce_mutation_policy(
        "version.checkpoint",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            _checkpoint_dry_run_payload(
                label=label,
                kind=kind,
                session_id=session_id,
                prompt_event_id=prompt_event_id,
            ),
            title="Checkpoint Dry Run",
        )
        return

    conn = get_connection(require_project=True, require_timeline=True)
    checkpoint = version_ops.create_checkpoint(
        conn,
        label=label,
        kind=kind,
        session_id=session_id,
        prompt_event_id=prompt_event_id,
        parent_checkpoint_id=parent_checkpoint_id,
    )
    output(checkpoint, title="Checkpoint", quiet_key="id")


@app.command("list")
@handle_errors
def list_checkpoints(
    project_name: Optional[str] = typer.Option(None, "--project-name", help="Filter by DaVinci Resolve project name"),
    timeline_name: Optional[str] = typer.Option(None, "--timeline-name", help="Filter by DaVinci Resolve timeline name"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Filter by CutAgent session id"),
):
    """List stored checkpoints."""
    enforce_mutation_policy("version.checkpoint", intended_engine="api_native", mutating=False)
    rows = version_ops.list_checkpoints(
        project_name=project_name,
        timeline_name=timeline_name,
        session_id=session_id,
    )
    output(
        rows,
        title="Checkpoints",
        columns=[
            ("id", "ID"),
            ("kind", "Kind"),
            ("project_name", "Project"),
            ("timeline_name", "Timeline"),
            ("label", "Label"),
            ("created_at", "Created"),
        ],
        quiet_key="id",
    )


@app.command("inspect")
@handle_errors
def inspect(checkpoint_id: str = typer.Argument(..., help="Checkpoint id")):
    """Inspect a checkpoint record."""
    enforce_mutation_policy("version.checkpoint", intended_engine="api_native", mutating=False)
    output(version_ops.inspect_checkpoint(checkpoint_id), title="Checkpoint")


@app.command("prune")
@handle_errors
def prune(
    session_id: str = typer.Option(..., "--session-id", help="CutAgent session id whose checkpoints should be removed"),
):
    """Prune stored checkpoints for a deleted CutAgent session."""
    enforce_mutation_policy(
        "version.checkpoint",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("manual")
        output(
            mutation_payload(
                action="version.prune",
                changed=False,
                target={"kind": "checkpoint_session", "session_id": session_id},
                message="DRY-RUN: Would prune checkpoints for the CutAgent session.",
            ),
            title="Prune Dry Run",
        )
        return

    result = version_ops.prune_checkpoints_for_session(session_id)
    output(result, title="Prune Checkpoints")


@app.command("restore")
@handle_errors
def restore(
    checkpoint_id: str = typer.Argument(..., help="Checkpoint id"),
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Require the checkpoint to belong to this CutAgent session id"),
    expected_current_state_hash: Optional[str] = typer.Option(
        None,
        "--expected-current-state-hash",
        hidden=True,
    ),
):
    """Restore a checkpoint by replacing its local Disk Project.db snapshot."""
    if expected_current_state_hash is not None and re.fullmatch(
        r"sha256:[a-f0-9]{64}", expected_current_state_hash
    ) is None:
        raise ValidationError(
            "Expected current state hash must be one exact SHA-256 digest.",
            details={"reason": "invalid_expected_current_state_hash"},
            recoverability="not_applicable",
        )
    enforce_mutation_policy(
        "version.checkpoint",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("manual")
        output(
            mutation_payload(
                action="version.restore",
                changed=False,
                target={"kind": "checkpoint", "id": checkpoint_id, "session_id": session_id},
                message="DRY-RUN: Would validate the checkpoint and restore its Project.db snapshot.",
            ),
            title="Restore Dry Run",
        )
        return

    conn = get_connection(require_project=False)
    result = version_ops.restore_checkpoint(
        conn,
        checkpoint_id,
        session_id=session_id,
        expected_current_state_hash=expected_current_state_hash,
    )
    message = (
        f"Restored project checkpoint: {result.get('restored_project_name')}"
        if result.get("reopened") is not False
        else f"Restored project checkpoint on disk: {result.get('restored_project_name')}"
    )
    output(
        mutation_payload(
            action="version.restore",
            changed=True,
            target={"kind": "project", "name": result.get("restored_project_name")},
            checkpoint=result.get("checkpoint"),
            restore_strategy=result.get("restore_strategy"),
            restored_project_name=result.get("restored_project_name"),
            project_db_path=result.get("project_db_path"),
            backup_path=result.get("backup_path"),
            restored_timeline_name=result.get("restored_timeline_name"),
            restored_on_disk=result.get("restored_on_disk"),
            reopened=result.get("reopened"),
            reopen_error=result.get("reopen_error"),
            steps=result.get("steps"),
            verified=result.get("verified"),
            verification_status=result.get("verification_status"),
            message=message,
        ),
        title="Restore",
    )


@app.command("status")
@handle_errors
def status(
    session_id: Optional[str] = typer.Option(None, "--session-id", help="Compare only against checkpoints for this session"),
):
    """Show whether the active project DB differs from the latest checkpoint."""
    enforce_mutation_policy("version.checkpoint", intended_engine="api_native", mutating=False)
    conn = get_connection(require_project=True, require_timeline=True)
    output(version_ops.version_status(conn, session_id=session_id), title="Version Status")
