"""DaVinci Resolve 20+ Free connection commands."""

from __future__ import annotations

from pathlib import Path

import typer

from ..adapters import embedded_status_timeout_seconds
from ..embedded_bridge import (
    EmbeddedBridgeClient,
    embedded_auth_token_status,
    embedded_host,
    embedded_port,
    install_script,
    installed_script_status,
    plan_install_script,
    run_embedded_server,
    script_install_path,
    uninstall_script,
)
from ..errors import ConfirmationRequired, handle_errors
from ..output import is_dry_run, is_machine_mode, output

app = typer.Typer(help="Connect CutAgent SDK to DaVinci Resolve 20+ Free.")


@app.command("status")
@handle_errors
def embedded_status():
    """Show the CutAgent SDK connection for DaVinci Resolve Free."""
    client = EmbeddedBridgeClient(timeout=embedded_status_timeout_seconds())
    server_status = client.status()
    auth_status = embedded_auth_token_status()
    output(
        {
            **installed_script_status(),
            "server": server_status,
            "auth": auth_status,
            "auth_path": auth_status["auth_path"],
            "auth_token_present": auth_status["auth_token_present"],
            "auth_token_valid": auth_status["auth_token_valid"],
            "connected": bool(server_status.get("connected")),
        },
        title="DaVinci Resolve Free Connection",
    )


@app.command("install")
@handle_errors
def embedded_install(
    sandbox: bool = typer.Option(False, "--sandbox", help="Install into the App Store sandbox container path"),
):
    """Install or update CutAgent SDK support in DaVinci Resolve Free."""
    result = plan_install_script(sandbox=sandbox) if is_dry_run() else install_script(sandbox=sandbox)
    output(result, title="CutAgent SDK Script Install")


@app.command("uninstall")
@handle_errors
def embedded_uninstall(
    sandbox: bool = typer.Option(False, "--sandbox", help="Remove from the App Store sandbox container path"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Remove CutAgent SDK support from DaVinci Resolve Free."""
    target = Path(script_install_path(sandbox=sandbox))
    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode uninstall requires --force.",
                details={"target": str(target), "sandbox": sandbox},
            )
        typer.confirm(f"Remove {target}?", abort=True)
    result = uninstall_script(sandbox=sandbox)
    output(result, title="CutAgent SDK Script Uninstall")


@app.command("start-server")
@handle_errors
def embedded_start_server(
    host: str = typer.Option(embedded_host(), "--host", help="Host to bind"),
    port: int = typer.Option(embedded_port(), "--port", help="Port to bind"),
    request_timeout_s: float | None = typer.Option(None, "--request-timeout-s", help="Lua request timeout"),
):
    """Keep the local connection to DaVinci Resolve Free open."""
    run_embedded_server(host=host, port=port, request_timeout=request_timeout_s)


@app.command("ping")
@handle_errors
def embedded_ping():
    """Check the connection to DaVinci Resolve Free."""
    output(EmbeddedBridgeClient(timeout=2.0).ping(), title="DaVinci Resolve Free Connection")
