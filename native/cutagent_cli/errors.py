"""Custom exceptions and error handling for cutagent-cli."""

from __future__ import annotations

import functools
import sys
from typing import Callable, Optional, Any

import typer
from rich.console import Console

from .machine_error_registry import fail_closed_recoverability

console = Console(stderr=True)


class CLIError(Exception):
    """Base CLI error with user-friendly message."""

    message: str = "An error occurred."
    code: str = "INTERNAL_ERROR"
    recoverability: str = "fatal"
    exit_code: int = 1
    suggested_fix: str | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Optional[dict[str, Any]] = None,
        recoverability: str | None = None,
        suggested_fix: str | None = None,
    ):
        final_message = self.message if message is None else _safe_error_message_text(message, fallback=self.message)
        super().__init__(final_message)
        self.details = details or {}
        self.recoverability = fail_closed_recoverability(
            self.code,
            recoverability or self.recoverability,
        )
        self.suggested_fix = suggested_fix or self.suggested_fix


def _safe_error_message_text(value: Any, *, fallback: str) -> str:
    """Best-effort string conversion for error messages."""
    try:
        text = str(value)
        if isinstance(text, str) and text:
            return text
    except Exception:
        pass

    for candidate in (getattr(value, "message", None), fallback, value.__class__.__name__ if value is not None else None):
        if isinstance(candidate, str) and candidate:
            return candidate
    return "Unexpected error."


class ResolveNotRunning(CLIError):
    message = "DaVinci Resolve is not running. Start it first."
    code = "RESOLVE_NOT_RUNNING"
    recoverability = "manual"
    exit_code = 3


class ResolveScriptingUnavailable(CLIError):
    message = (
        "DaVinci Resolve is running, but CutAgent SDK is not connected. "
        "For DaVinci Resolve Studio, enable Preferences > System > General > "
        "External scripting using Local, restart DaVinci Resolve, then retry. "
        "For DaVinci Resolve Free, run Workspace > Scripts > CutAgentSDK."
    )
    code = "RESOLVE_SCRIPTING_UNAVAILABLE"
    recoverability = "manual"
    exit_code = 3


class EmbeddedBridgeNotRunning(CLIError):
    message = "CutAgent SDK is not connected to DaVinci Resolve Free. In DaVinci Resolve, run Workspace > Scripts > CutAgentSDK."
    code = "EMBEDDED_BRIDGE_NOT_RUNNING"
    recoverability = "manual"
    exit_code = 3


class EmbeddedBridgeOutdated(CLIError):
    message = "CutAgentSDK.lua is out of date. Run `cutagent embedded install` again."
    code = "EMBEDDED_BRIDGE_OUTDATED"
    recoverability = "manual"
    exit_code = 3


class EmbeddedBridgeTimeout(CLIError):
    message = "CutAgent SDK did not receive a response from DaVinci Resolve Free in time."
    code = "EMBEDDED_BRIDGE_TIMEOUT"
    recoverability = "manual"
    exit_code = 4


class EmbeddedBridgeAuthFailed(CLIError):
    message = "CutAgent SDK could not verify the connection to DaVinci Resolve Free."
    code = "EMBEDDED_BRIDGE_AUTH_FAILED"
    recoverability = "manual"
    exit_code = 2


class EmbeddedBridgePolicyDenied(CLIError):
    message = "CutAgent SDK did not run this edit because its safety checks did not pass."
    code = "EMBEDDED_BRIDGE_POLICY_DENIED"
    recoverability = "not_applicable"
    exit_code = 2


class NoProjectOpen(CLIError):
    message = "No project is open in DaVinci Resolve."
    code = "NO_PROJECT_OPEN"
    recoverability = "manual"
    exit_code = 4


class NoTimelineOpen(CLIError):
    message = "No timeline is active. Create or open one first."
    code = "NO_TIMELINE_OPEN"
    recoverability = "manual"
    exit_code = 4


class APICallFailed(CLIError):
    message = "DaVinci Resolve API call failed."
    code = "API_CALL_FAILED"
    recoverability = "manual"
    exit_code = 4


class AssetNotFound(CLIError):
    message = "No candidate asset resolved."
    code = "ASSET_NOT_FOUND"
    recoverability = "manual"
    exit_code = 4


class MediaPoolItemNotFound(CLIError):
    message = "Media Pool item was not found."
    code = "MEDIA_POOL_ITEM_NOT_FOUND"
    recoverability = "manual"
    exit_code = 4


class AmbiguousMediaPoolItem(CLIError):
    message = "Media Pool item reference is ambiguous."
    code = "AMBIGUOUS_MEDIA_POOL_ITEM"
    recoverability = "manual"
    exit_code = 2


class TemplateFieldNotFound(CLIError):
    message = "Requested template field was not found."
    code = "TEMPLATE_FIELD_NOT_FOUND"
    recoverability = "manual"
    exit_code = 4


class TempAppendNotAllowed(CLIError):
    message = "Temporary timeline append is required but not allowed."
    code = "TEMP_APPEND_NOT_ALLOWED"
    recoverability = "manual"
    exit_code = 2


class TempAppendFailed(CLIError):
    message = "Temporary timeline append failed."
    code = "TEMP_APPEND_FAILED"
    recoverability = "manual"
    exit_code = 4


class TempCleanupFailed(CLIError):
    message = "Temporary timeline cleanup failed."
    code = "TEMP_CLEANUP_FAILED"
    recoverability = "manual"
    exit_code = 4


class TemplateNotFound(CLIError):
    message = "Template not found in Media Pool."
    code = "VALIDATION_ERROR"
    recoverability = "manual"
    exit_code = 2


class FolderNotFound(CLIError):
    message = "Folder not found in Media Pool."
    code = "VALIDATION_ERROR"
    recoverability = "manual"
    exit_code = 2


class ClipNotFound(CLIError):
    message = "Clip not found."
    code = "CLIP_NOT_FOUND"
    recoverability = "manual"
    exit_code = 4


class InvalidTimeReference(CLIError):
    message = "Invalid time reference."
    code = "INVALID_TIME_REFERENCE"
    recoverability = "manual"
    exit_code = 2


class ExternalToolNotFound(CLIError):
    message = "Required external tool not found."
    code = "EXTERNAL_TOOL_NOT_FOUND"
    recoverability = "manual"
    exit_code = 3


class ReadinessFailed(CLIError):
    message = "Environment readiness checks failed."
    code = "READINESS_FAILED"
    recoverability = "manual"
    exit_code = 3


class ValidationError(CLIError):
    message = "Validation failed."
    code = "VALIDATION_ERROR"
    recoverability = "manual"
    exit_code = 2


class TimelineConflict(CLIError):
    message = "Timeline conflict."
    code = "TIMELINE_CONFLICT"
    recoverability = "manual"
    exit_code = 2


class EditMutationFailedBeforeChange(CLIError):
    message = "Edit mutation failed before changing the timeline."
    code = "EDIT_MUTATION_FAILED_BEFORE_CHANGE"
    recoverability = "manual"
    exit_code = 4


class AmbiguousTimelineItem(CLIError):
    message = "Timeline item selector matched more than one item."
    code = "AMBIGUOUS_TIMELINE_ITEM"
    recoverability = "manual"
    exit_code = 2


class StaleTimelineItem(CLIError):
    message = "Timeline item target changed before mutation."
    code = "STALE_TIMELINE_ITEM"
    recoverability = "manual"
    exit_code = 4


class SdkMutationStaleRevision(CLIError):
    """The SDK mutation precondition no longer matches live DaVinci Resolve state."""

    message = "The SDK mutation target changed before execution."
    code = "STALE_REVISION"
    recoverability = "retryable"
    exit_code = 4


class EditMutationRestored(CLIError):
    message = "Edit mutation failed and the checkpoint was restored."
    code = "EDIT_MUTATION_RESTORED"
    recoverability = "manual"
    exit_code = 4


class EffectNotSupported(CLIError):
    message = "The requested effect is not in the reviewed effect registry."
    code = "EFFECT_NOT_SUPPORTED"
    recoverability = "manual"
    exit_code = 2


class EffectParameterInvalid(CLIError):
    message = "An effect parameter is unsupported or outside its reviewed type and range."
    code = "EFFECT_PARAMETER_INVALID"
    recoverability = "manual"
    exit_code = 2


class EffectVerificationFailed(CLIError):
    message = "Effect application could not be verified through structural and rendered evidence."
    code = "EFFECT_VERIFICATION_FAILED"
    recoverability = "manual"
    exit_code = 4


class EditMutationPartiallyApplied(CLIError):
    message = "Edit mutation was partially applied."
    code = "EDIT_MUTATION_PARTIALLY_APPLIED"
    recoverability = "manual"
    exit_code = 4


class EditMutationRecoveryFailed(APICallFailed):
    message = "Edit mutation recovery failed."
    code = "EDIT_MUTATION_RECOVERY_FAILED"
    recoverability = "manual"
    exit_code = 4


class SmartReframeVerificationFailed(CLIError):
    message = "Smart Reframe returned, but terminal rendered evidence did not verify the reframing."
    code = "SMART_REFRAME_VERIFICATION_FAILED"
    recoverability = "manual"
    exit_code = 4


class MissingArgumentError(CLIError):
    message = "Required argument is missing."
    code = "MISSING_ARGUMENT"
    recoverability = "manual"
    exit_code = 2


class PolicyDenied(CLIError):
    message = "Operation blocked by active policy profile."
    code = "POLICY_DENIED"
    recoverability = "not_applicable"
    exit_code = 2


class AuthorizationError(CLIError):
    message = "DaVinci Resolve command authorization failed."
    code = "AUTH_TOKEN_INVALID"
    recoverability = "manual"
    exit_code = 2
    suggested_fix = "Retry the command. If the problem persists, restart the CutAgent app."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Optional[dict[str, Any]] = None,
        suggested_fix: str | None = None,
    ):
        super().__init__(message, details=details, suggested_fix=suggested_fix)
        if code:
            self.code = code


class HostedServiceRequiresCutAgentApp(AuthorizationError):
    message = "This feature is available in the CutAgent desktop app. Explore plans: https://cutagent.ai."
    code = "HOSTED_SERVICE_REQUIRES_CUTAGENT_APP"
    recoverability = "manual"
    exit_code = 4
    suggested_fix = "Explore the CutAgent desktop app at https://cutagent.ai."


class AuthRequired(AuthorizationError):
    message = "CutAgent SDK could not verify this command."
    code = "AUTH_REQUIRED"
    suggested_fix = "Run the command again using the installed cutagent command."


class AuthTokenExpired(AuthorizationError):
    message = "CutAgent SDK could not verify this command because it took too long."
    code = "AUTH_TOKEN_EXPIRED"
    suggested_fix = "Run the command again using the installed cutagent command."


class AuthTokenCommandMismatch(AuthorizationError):
    message = "CutAgent SDK could not verify this command."
    code = "AUTH_TOKEN_COMMAND_MISMATCH"


class SubscriptionRequired(AuthorizationError):
    message = "This feature is available in the CutAgent desktop app. Explore plans: https://cutagent.ai."
    code = "SUBSCRIPTION_REQUIRED"
    suggested_fix = "Explore the CutAgent desktop app at https://cutagent.ai."


class CapabilityNegotiationFailed(CLIError):
    message = "Capability negotiation failed for this operation."
    code = "CAPABILITY_NEGOTIATION_FAILED"
    recoverability = "manual"
    exit_code = 2


class ConfirmationRequired(CLIError):
    message = "Operation requires explicit confirmation."
    code = "CONFIRMATION_REQUIRED"
    recoverability = "manual"
    exit_code = 2


class DiskDbLocked(CLIError):
    message = "Disk project database is locked by another operation."
    code = "DB_LOCKED"
    recoverability = "retryable"
    exit_code = 4


class StaleDbMulticam(CLIError):
    message = "Target native multicam has stale Disk Project.db records."
    code = "STALE_DB_MULTICAM"
    recoverability = "manual"
    exit_code = 4


class GuiPermissionMissing(CLIError):
    message = "Required macOS GUI permissions are missing."
    code = "GUI_PERMISSION_MISSING"
    recoverability = "manual"
    exit_code = 3


class ResolveWindowNotFound(CLIError):
    message = "DaVinci Resolve window was not found."
    code = "RESOLVE_WINDOW_NOT_FOUND"
    recoverability = "manual"
    exit_code = 4


class ResolveWindowNotReady(CLIError):
    message = "DaVinci Resolve window is not ready for GUI-assisted execution."
    code = "RESOLVE_WINDOW_NOT_READY"
    recoverability = "manual"
    exit_code = 4


class ColorPageNotReady(CLIError):
    message = "DaVinci Resolve Color page is not ready."
    code = "COLOR_PAGE_NOT_READY"
    recoverability = "manual"
    exit_code = 4


class ColorRenderProofRequired(CLIError):
    message = "Color command readback is not sufficient proof that the rendered image changed."
    code = "COLOR_RENDER_PROOF_REQUIRED"
    recoverability = "manual"
    exit_code = 4
    suggested_fix = "Use a color route with rendered-frame proof, or verify exported/rendered frames before continuing."


class ColorRenderProofFailed(CLIError):
    message = "Color command completed, but rendered-frame proof did not show any pixel change."
    code = "COLOR_RENDER_PROOF_FAILED"
    recoverability = "manual"
    exit_code = 4
    suggested_fix = "Inspect the before/after proof frames, then use a render-visible grade route or a stronger non-idempotent change."


class MagicMaskPanelNotReady(CLIError):
    message = "DaVinci Resolve Magic Mask panel is not ready."
    code = "MAGIC_MASK_PANEL_NOT_READY"
    recoverability = "manual"
    exit_code = 4


class ColorPagePanelNotReady(CLIError):
    message = "DaVinci Resolve Color page panel is not ready."
    code = "COLOR_PAGE_PANEL_NOT_READY"
    recoverability = "manual"
    exit_code = 4


class ViewerGeometryNotFound(CLIError):
    message = "DaVinci Resolve viewer geometry could not be determined."
    code = "VIEWER_GEOMETRY_NOT_FOUND"
    recoverability = "manual"
    exit_code = 4


class StrokeMappingFailed(CLIError):
    message = "Magic Mask stroke could not be mapped to viewer coordinates."
    code = "STROKE_MAPPING_FAILED"
    recoverability = "manual"
    exit_code = 4


class MagicMaskTrackFailed(CLIError):
    message = "Magic Mask tracking failed."
    code = "MAGIC_MASK_TRACK_FAILED"
    recoverability = "manual"
    exit_code = 4


class ColorPageTrackFailed(CLIError):
    message = "DaVinci Resolve Color page tracking failed."
    code = "COLOR_PAGE_TRACK_FAILED"
    recoverability = "manual"
    exit_code = 4


class MagicMaskProofFailed(CLIError):
    message = "Magic Mask proof artifact generation failed."
    code = "MAGIC_MASK_PROOF_FAILED"
    recoverability = "manual"
    exit_code = 4


class ColorPageGuiProofFailed(CLIError):
    message = "DaVinci Resolve Color page GUI proof artifact generation failed."
    code = "COLOR_PAGE_GUI_PROOF_FAILED"
    recoverability = "manual"
    exit_code = 4


def _nonzero_exit_code(value: Any, *, default: int = 1) -> int:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return default
    return code if code > 0 else default


def handle_errors(func: Callable) -> Callable:
    """Decorator for CLI commands — catches CLIError and exits cleanly."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CLIError as exc:
            from .output import fail_active_verification_status, json_error, get_output_mode, set_recoverability

            fail_active_verification_status()
            exc.recoverability = fail_closed_recoverability(exc.code, exc.recoverability)
            set_recoverability(exc.recoverability)
            message = _safe_error_message_text(exc, fallback=exc.message)
            if get_output_mode() == "json":
                json_error(code=exc.code, message=message, details=exc.details, suggested_fix=exc.suggested_fix)
            else:
                console.print(f"[bold red]Error:[/bold red] {message}")
                if exc.suggested_fix:
                    console.print(f"[yellow]Fix:[/yellow] {exc.suggested_fix}")
            raise typer.Exit(_nonzero_exit_code(exc.exit_code))
        except KeyboardInterrupt:
            from .output import json_error, get_output_mode, set_recoverability, set_verification_status

            set_verification_status("failed")
            set_recoverability("manual")
            if get_output_mode() == "json":
                json_error(code="INTERNAL_ERROR", message="Interrupted.", details={})
            else:
                console.print("\n[dim]Interrupted.[/dim]")
            raise typer.Exit(130)
        except typer.Abort:
            from .output import get_output_mode, json_error, set_recoverability, set_verification_status

            set_verification_status("failed")
            set_recoverability("not_applicable")
            if get_output_mode() == "json":
                json_error(code="ABORTED", message="Canceled.", details={})
            else:
                console.print("[yellow]Canceled.[/yellow]")
            raise typer.Exit(1)
        except Exception as exc:
            from .output import json_error, get_output_mode, set_recoverability, set_verification_status

            set_verification_status("failed")
            set_recoverability("fatal")
            message = _safe_error_message_text(exc, fallback=exc.__class__.__name__)
            if get_output_mode() == "json":
                details = {"type": exc.__class__.__name__}
                if "--verbose" in sys.argv or "-v" in sys.argv:
                    details["repr"] = repr(exc)
                json_error(code="INTERNAL_ERROR", message=message, details=details)
            else:
                console.print(f"[bold red]Unexpected error:[/bold red] {message}")
                if "--verbose" in sys.argv or "-v" in sys.argv:
                    console.print_exception()
            raise typer.Exit(1)
        finally:
            from .output import set_dry_run

            set_dry_run(False)

    return wrapper
