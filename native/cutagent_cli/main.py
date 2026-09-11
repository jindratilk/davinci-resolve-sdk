"""cutagent - contract-aware CutAgent CLI."""

from __future__ import annotations

import logging
import os
import sys
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, Optional

import click
import typer
from typer.main import get_command
from typer.core import TyperGroup

from . import __version__
from .config import get_config
from .commands import (
    asset,
    auto_edit,
    audio,
    batch,
    bulk,
    burnin,
    clip,
    codec,
    color,
    dctl,
    developer,
    edit,
    embedded,
    fairlight,
    fuse,
    fusion,
    lut,
    media,
    multicam,
    ofx,
    page,
    project,
    render,
    script,
    storage,
    system,
    text,
    timeline,
    transcript,
    utility,
    video,
    version as version_commands,
    workflow,
)
from .authz import authorization_required, is_local_status_probe, verify_command_authorization
from .errors import AuthorizationError, ValidationError, handle_errors
from .external_tools import set_tool_override
from .output import (
    set_output_mode,
    set_select_fields,
    set_dry_run,
    set_command_context,
    set_capability_context,
    set_execution_engine,
    set_verbose,
    set_lean,
    json_error,
    output,
    is_dry_run,
    is_machine_mode,
    has_response_emitted,
)
from .policy import configure_policy, enforce_mutation_policy
from .core import launch_ops

_GLOBAL_FLAG_OPTIONS = {
    "--json",
    "-j",
    "--agent",
    "--lean",
    "--quiet",
    "-q",
    "--plain",
    "-p",
    "--tsv",
    "--dry-run",
    "-n",
    "--verbose",
    "-v",
}

_OUTPUT_MODES = {"json", "table", "plain", "quiet", "agent"}
_OUTPUT_DEFAULT_ENV = "CUTAGENT_CLI_OUTPUT_DEFAULT"
_SDK_READ_DISPATCH = ContextVar("cutagent_sdk_read_dispatch", default=False)


def _env_default_output_mode() -> Optional[str]:
    """Default output mode from the environment (set by the CutAgent runtime).

    Explicit CLI flags always win; this only applies when no mode flag is given.
    """
    import os

    value = os.environ.get(_OUTPUT_DEFAULT_ENV, "").strip().lower()
    return value if value in _OUTPUT_MODES else None

_GLOBAL_VALUE_OPTIONS = {
    "--output-mode",
    "--select",
    "--policy-profile",
    "--ffmpeg-path",
    "--ffprobe-path",
}


def _tokens_before_double_dash(args: list[str]) -> list[str]:
    if "--" not in args:
        return args
    return args[: args.index("--")]


def _global_flag_requested(args: list[str], flags: set[str]) -> bool:
    return any(token in flags for token in _tokens_before_double_dash(args))


def _explicit_output_mode(args: list[str]) -> Optional[str]:
    """Return the output mode explicitly requested on the command line, if any."""
    hoisted = _hoist_global_options(list(args))
    tokens = _tokens_before_double_dash(hoisted)
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == "--output-mode":
            if i + 1 < len(tokens) and tokens[i + 1] in _OUTPUT_MODES:
                return tokens[i + 1]
        elif token.startswith("--output-mode="):
            value = token.partition("=")[2]
            if value in _OUTPUT_MODES:
                return value
        elif token in {"--json", "-j"}:
            return "json"
        elif token == "--agent":
            return "agent"
        elif token in {"--quiet", "-q"}:
            return "quiet"
        elif token in {"--plain", "-p", "--tsv"}:
            return "plain"
        i += 1
    return None


def _requested_machine_mode(args: list[str]) -> Optional[str]:
    """Return "json"/"agent" when a machine mode is in effect, else None."""
    mode = _explicit_output_mode(args) or _env_default_output_mode()
    return mode if mode in {"json", "agent"} else None


def _machine_mode_requested(args: list[str]) -> bool:
    return _requested_machine_mode(args) is not None


def _help_requested(args: list[str]) -> bool:
    """Return True if ``--help`` or ``-h`` appears in *args*."""
    return _global_flag_requested(args, {"--help", "-h"})


def _version_requested(args: list[str]) -> bool:
    return _global_flag_requested(args, {"--version"})


def _authorization_exempt(args: list[str]) -> bool:
    normalized_args = _hoist_global_options(list(args))
    return (
        _help_requested(normalized_args)
        or _version_requested(normalized_args)
        or not _has_subcommand(normalized_args)
        or is_local_status_probe(normalized_args)
    )


def _require_command_authorization(args: list[str]) -> None:
    if _SDK_READ_DISPATCH.get():
        return
    if _authorization_exempt(args) and not os.environ.get("CUTAGENT_CLI_AUTH_TOKEN", "").strip():
        return
    command_id = infer_canonical_command_id(args)
    if command_id in {"audio.voice_list", "audio.voice_generate", "transcript.create", "video.generate"}:
        from .standalone_hosted import unavailable

        service = {
            "audio.voice_list": "voice_catalog",
            "audio.voice_generate": "voice_generation",
            "transcript.create": "transcription",
            "video.generate": "video_generation",
        }[command_id]
        unavailable(service)
    verify_command_authorization(
        command_id,
        accept_compiled_import_redemption=True,
    )


def _has_subcommand(args: list[str]) -> bool:
    """Return True if *args* contains at least one non-option token (a subcommand)."""
    for token in args:
        if token == "--":
            break
        if not token.startswith("-"):
            return True
    return False


def _canonicalize_segment(segment: str) -> str:
    return segment.replace("-", "_")


def _canonicalize_command_path_segment(command_tokens: list[str], segment: str) -> str:
    canonical = _canonicalize_segment(segment)
    if command_tokens == ["timeline"] and canonical == "tracks":
        return "track"
    return canonical


@lru_cache(maxsize=1)
def _command_catalog_index() -> tuple[dict[str, str], dict[str, Any], set[str]]:
    try:
        from .command_catalog import get_command_catalog

        command_by_path = {}
        command_object_by_path = {}
        for command in get_command_catalog():
            if not str(command.path) or not str(command.command_id):
                continue
            path_id = ".".join(_canonicalize_segment(part) for part in str(command.path).split())
            command_by_path[path_id] = str(command.command_id)
            command_object_by_path[path_id] = command
    except Exception:
        return {}, {}, set()

    prefixes: set[str] = set()
    for path_id in command_by_path:
        parts = path_id.split(".")
        for index in range(1, len(parts)):
            prefixes.add(".".join(parts[:index]))
    return command_by_path, command_object_by_path, prefixes


def _command_from_catalog_args(args: list[str]) -> Any | None:
    command_by_path, command_object_by_path, prefixes = _command_catalog_index()
    if not command_by_path:
        return None

    tokens = _hoist_global_options(list(args))
    command_tokens: list[str] = []
    best_path_id: str | None = None
    timeline_tracks_alias = False

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _GLOBAL_VALUE_OPTIONS:
            index += 2
            continue
        if any(token.startswith(f"{opt}=") for opt in _GLOBAL_VALUE_OPTIONS):
            index += 1
            continue
        if token == "--" or token.startswith("-"):
            index += 1
            continue

        canonical_token = _canonicalize_command_path_segment(command_tokens, token)
        if command_tokens == ["timeline"] and _canonicalize_segment(token) == "tracks":
            timeline_tracks_alias = True
        candidate = ".".join([*command_tokens, canonical_token])
        if candidate not in command_by_path and candidate not in prefixes:
            break
        command_tokens.append(canonical_token)
        if candidate in command_by_path:
            best_path_id = candidate
        index += 1

    if best_path_id is None and timeline_tracks_alias and command_tokens == ["timeline", "track"] and not _help_requested(tokens):
        best_path_id = "timeline.track.list"

    return command_object_by_path.get(best_path_id) if best_path_id else None


def _command_from_catalog_path(command_path: str) -> Any | None:
    if not command_path:
        return None
    _command_by_path, command_object_by_path, _prefixes = _command_catalog_index()
    path_id = ".".join(_canonicalize_segment(part) for part in command_path.split())
    return command_object_by_path.get(path_id)


def _command_id_from_catalog_args(args: list[str]) -> str | None:
    command = _command_from_catalog_args(args)
    return str(command.command_id) if command is not None and str(command.command_id) else None


def _command_tokens_from_args(args: list[str]) -> list[str]:
    tokens = _hoist_global_options(list(args))
    command: click.Command = get_command(app)
    command_tokens: list[str] = []
    timeline_tracks_alias = False

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in _GLOBAL_VALUE_OPTIONS:
            i += 2
            continue
        if any(token.startswith(f"{opt}=") for opt in _GLOBAL_VALUE_OPTIONS):
            i += 1
            continue
        if token == "--" or token.startswith("-"):
            i += 1
            continue
        commands = getattr(command, "commands", None)
        if not isinstance(commands, dict) or token not in commands:
            if command_tokens == ["fusion"] and token == "insert-settings" and i + 1 < len(tokens) and tokens[i + 1] == "batch":
                command_tokens.extend(["insert-settings", "batch"])
                i += 2
                break
            if command_tokens in (
                ["media", "append"],
                ["timeline", "frame-export"],
            ) and token == "batch":
                command_tokens.append(token)
                i += 1
            break
        canonical_token = _canonicalize_command_path_segment(command_tokens, token)
        if command_tokens == ["timeline"] and _canonicalize_segment(token) == "tracks":
            timeline_tracks_alias = True
        command_tokens.append(canonical_token)
        command = commands[token]
        i += 1

    if timeline_tracks_alias and command_tokens == ["timeline", "track"] and not _help_requested(tokens):
        return [*command_tokens, "list"]

    return command_tokens


def _machine_help_payload(args: list[str]) -> dict[str, object] | None:
    """Return structured command metadata for exact command help in machine mode."""
    command = _command_from_catalog_args(args)
    if command is None:
        command = _command_from_catalog_path(" ".join(_command_tokens_from_args(args)))
    if command is None:
        return None

    payload = {
        "command_id": command.command_id,
        "path": command.path,
        "summary": command.help_text or command.doc or "",
        "docs_topic": command.docs_topic,
        "source_file": command.source_file,
        "function_name": command.function_name,
        "capability_id": command.capability_id,
        "capability_status": command.capability_status,
        "engine": command.engine,
        "parameters": [
            {
                "name": parameter.python_name,
                "kind": parameter.kind,
                "cli_names": list(parameter.cli_names),
                "help": parameter.help_text,
                "default": parameter.default,
                "annotation": parameter.annotation,
            }
            for parameter in command.parameters
        ],
    }
    if command.capability_caveats:
        payload["capability_caveats"] = dict(command.capability_caveats)
    return payload


def _apply_machine_command_metadata(args: list[str]) -> None:
    """Best-effort command metadata for parser errors that happen before command code runs."""
    command = _command_from_catalog_args(args)
    if command is None:
        command = _command_from_catalog_path(" ".join(_command_tokens_from_args(args)))
    if command is None:
        return

    if command.engine:
        set_execution_engine(command.engine)
    set_capability_context(command.capability_id, command.capability_status)


def infer_canonical_command_id(args: list[str] | None = None) -> str:
    arg_list = sys.argv[1:] if args is None else args
    if "sdk-action-read" in arg_list or "sdk-evaluator-sound-library-observe" in arg_list:
        return "sdk.low_level.read"
    catalog_command_id = _command_id_from_catalog_args(arg_list)
    if catalog_command_id:
        return catalog_command_id
    command_tokens = _command_tokens_from_args(arg_list)
    if not command_tokens:
        return "cutagent_cli"
    return ".".join(_canonicalize_segment(token) for token in command_tokens)


def _machine_error_code(exc: BaseException) -> str:
    no_such_command_type = getattr(click.exceptions, "NoSuchCommand", ())
    if isinstance(exc, click.exceptions.NoSuchOption):
        return "INVALID_OPTION"
    if no_such_command_type and isinstance(exc, no_such_command_type):
        return "UNKNOWN_COMMAND"
    if isinstance(exc, click.exceptions.MissingParameter):
        return "MISSING_ARGUMENT"
    if isinstance(exc, (click.exceptions.BadParameter, click.exceptions.BadOptionUsage, click.exceptions.BadArgumentUsage)):
        return "VALIDATION_ERROR"
    if isinstance(exc, click.exceptions.UsageError) and str(exc).lower().startswith("no such command"):
        return "UNKNOWN_COMMAND"
    if isinstance(exc, click.exceptions.UsageError):
        return "USAGE_ERROR"
    if isinstance(exc, click.Abort):
        return "ABORTED"
    return "INTERNAL_ERROR"


def _command_tokens_without_global_options(args: list[str]) -> list[str]:
    tokens: list[str] = []
    skip_next = False
    for token in args:
        if skip_next:
            skip_next = False
            continue
        if token in _GLOBAL_FLAG_OPTIONS:
            continue
        if token in _GLOBAL_VALUE_OPTIONS:
            skip_next = True
            continue
        if any(token.startswith(f"{option}=") for option in _GLOBAL_VALUE_OPTIONS):
            continue
        tokens.append(token)
    return tokens


def _add_command_specific_error_hints(details: dict[str, object], exc: BaseException, args: Optional[list[str]]) -> None:
    if not args:
        return
    command_tokens = _command_tokens_without_global_options(args)
    if command_tokens[:3] == ["clip", "fusion", "export"] and details.get("parameter") == "index":
        details.setdefault("hint", "Expected composition index first, then the output .setting path.")
        details.setdefault("example", 'cutagent -j clip fusion export 1 /abs/path/out.setting --clip "Clip Name"')
        details.setdefault("argument_order", ["index", "path", "--clip"])


def _machine_error_details(exc: BaseException, args: Optional[list[str]] = None) -> dict[str, object]:
    details: dict[str, object] = {}
    no_such_command_type = getattr(click.exceptions, "NoSuchCommand", ())
    if isinstance(exc, click.exceptions.NoSuchOption):
        details["option"] = exc.option_name
        if getattr(exc, "possibilities", None):
            details["allowed"] = list(exc.possibilities)
    elif no_such_command_type and isinstance(exc, no_such_command_type):
        details["command"] = getattr(exc, "cmd_name", None)
        if getattr(exc, "possibilities", None):
            details["allowed"] = list(exc.possibilities)
    elif isinstance(exc, click.exceptions.MissingParameter):
        param = getattr(exc, "param", None)
        if param is not None:
            details["parameter"] = getattr(param, "name", None)
            details["parameter_type"] = param.param_type_name
    elif isinstance(exc, click.exceptions.BadParameter):
        param = getattr(exc, "param", None)
        if param is not None:
            details["parameter"] = getattr(param, "name", None)
            details["parameter_type"] = param.param_type_name
    _add_command_specific_error_hints(details, exc, args)
    return {key: value for key, value in details.items() if value is not None}


def _hoist_global_options(args: list[str]) -> list[str]:
    """Move global options to root scope so they work after subcommands."""
    if not args:
        return args

    tail: list[str] = []
    if "--" in args:
        sep = args.index("--")
        tail = args[sep:]
        args = args[:sep]

    hoisted: list[str] = []
    remaining: list[str] = []

    i = 0
    while i < len(args):
        token = args[i]

        if token in _GLOBAL_FLAG_OPTIONS:
            hoisted.append(token)
            i += 1
            continue

        if token in _GLOBAL_VALUE_OPTIONS:
            hoisted.append(token)
            if i + 1 < len(args):
                hoisted.append(args[i + 1])
                i += 2
            else:
                i += 1
            continue

        if token.startswith("--"):
            matched = False
            for opt in _GLOBAL_VALUE_OPTIONS:
                prefix = f"{opt}="
                if token.startswith(prefix):
                    hoisted.append(token)
                    matched = True
                    break
            if matched:
                i += 1
                continue

        remaining.append(token)
        i += 1

    return hoisted + remaining + tail


def _emit_human_authorization_error(exc: AuthorizationError) -> None:
    """Render an authorization failure as a clean human-readable error."""
    from .errors import console as error_console

    error_console.print(f"[bold red]Error:[/bold red] {exc}")
    if exc.suggested_fix:
        error_console.print(f"[yellow]Fix:[/yellow] {exc.suggested_fix}")


class _RootOptionHoistGroup(TyperGroup):
    """Typer group that accepts root options after subcommands."""

    def parse_args(self, ctx, args: list[str]) -> list[str]:
        return super().parse_args(ctx, _hoist_global_options(args))

    def main(self, args=None, prog_name=None, complete_var=None, standalone_mode=True, windows_expand_args=True, **extra):
        prog_name = prog_name or "cutagent"
        normalized_args = _hoist_global_options(list(sys.argv[1:] if args is None else args))
        machine_mode = _requested_machine_mode(normalized_args)
        set_command_context(infer_canonical_command_id(normalized_args))
        if machine_mode is None:
            try:
                _require_command_authorization(normalized_args)
            except AuthorizationError as exc:
                # Render the failure directly: this runs before Click's
                # standalone handler exists, so a raised ClickException would
                # escape to sys.excepthook and dump a traceback.
                _emit_human_authorization_error(exc)
                if standalone_mode:
                    raise SystemExit(exc.exit_code)
                raise click.exceptions.Exit(exc.exit_code)
            return super().main(
                args=normalized_args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=standalone_mode,
                windows_expand_args=windows_expand_args,
                **extra,
            )

        # ---- Machine mode: guarantee JSON-only stdout ----

        # Pre-flight: detect --help before Click can emit plain-text help.
        if _help_requested(normalized_args):
            set_output_mode(machine_mode)
            set_command_context(infer_canonical_command_id(normalized_args))
            help_payload = _machine_help_payload(normalized_args)
            if help_payload is not None:
                engine = help_payload.get("engine")
                if isinstance(engine, str) and engine:
                    set_execution_engine(engine)
                capability_id = help_payload.get("capability_id")
                capability_status = help_payload.get("capability_status")
                set_capability_context(
                    capability_id if isinstance(capability_id, str) else None,
                    capability_status if isinstance(capability_status, str) else None,
                )
                output({"help": help_payload})
                if standalone_mode:
                    raise SystemExit(0)
                return None
            json_error(
                code="USAGE_ERROR",
                message="Help text is not available in machine mode. Remove --json to see human-readable help.",
                details={},
            )
            if standalone_mode:
                raise SystemExit(0)
            return None

        # Pre-flight: no subcommand supplied (e.g. `cutagent --json`).
        # Allow --version through since it is handled by the root callback.
        if not _has_subcommand(normalized_args) and "--version" not in normalized_args:
            set_output_mode(machine_mode)
            set_command_context(infer_canonical_command_id(normalized_args))
            json_error(
                code="USAGE_ERROR",
                message="No command specified. Pass a subcommand (e.g. 'project list').",
                details={},
            )
            if standalone_mode:
                raise SystemExit(2)
            return None

        try:
            _apply_machine_command_metadata(normalized_args)
            _require_command_authorization(normalized_args)
        except AuthorizationError as exc:
            set_output_mode(machine_mode)
            set_command_context(infer_canonical_command_id(normalized_args))
            _apply_machine_command_metadata(normalized_args)
            json_error(
                code=exc.code,
                message=str(exc),
                details=exc.details,
                suggested_fix=exc.suggested_fix,
            )
            if standalone_mode:
                raise SystemExit(exc.exit_code)
            raise click.exceptions.Exit(exc.exit_code)

        try:
            result = super().main(
                args=normalized_args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                windows_expand_args=windows_expand_args,
                **extra,
            )
            if isinstance(result, int):
                if result != 0:
                    if not has_response_emitted():
                        set_output_mode(machine_mode)
                        set_command_context(infer_canonical_command_id(normalized_args))
                        _apply_machine_command_metadata(normalized_args)
                        json_error(code="USAGE_ERROR", message="Command exited before producing a machine response.", details={})
                if standalone_mode:
                    raise SystemExit(result)
                if result != 0:
                    raise click.exceptions.Exit(result)
                return None
            return result
        except click.exceptions.Exit as exc:
            if exc.exit_code == 0:
                if standalone_mode:
                    raise SystemExit(0)
                return None
            if not has_response_emitted():
                set_output_mode(machine_mode)
                set_command_context(infer_canonical_command_id(normalized_args))
                _apply_machine_command_metadata(normalized_args)
                json_error(code="USAGE_ERROR", message="Command exited before producing a machine response.", details={})
            if standalone_mode:
                raise SystemExit(exc.exit_code)
            raise
        except SystemExit:
            raise
        except BaseException as exc:
            if not has_response_emitted():
                set_output_mode(machine_mode)
                set_command_context(infer_canonical_command_id(normalized_args))
                _apply_machine_command_metadata(normalized_args)
                json_error(
                    code=_machine_error_code(exc),
                    message=str(exc),
                    details=_machine_error_details(exc, normalized_args),
                )
            if standalone_mode:
                if isinstance(exc, click.ClickException):
                    raise SystemExit(exc.exit_code)
                if isinstance(exc, click.Abort):
                    raise SystemExit(1)
                raise
            raise


app = typer.Typer(
    name="cutagent",
    help="Contract-aware CutAgent CLI for CutAgent automation.",
    no_args_is_help=True,
    add_completion=True,
    cls=_RootOptionHoistGroup,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
)


@app.callback(invoke_without_command=True)
def main(
    output_mode: Optional[str] = typer.Option(
        None,
        "--output-mode",
        help="Output mode: json|table|plain|quiet|agent",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
    agent_output: bool = typer.Option(
        False,
        "--agent",
        help="Compact machine-readable text output for AI agents (same envelope, fewer tokens)",
    ),
    lean: bool = typer.Option(
        False,
        "--lean",
        help="Lean JSON: omit null meta fields from the envelope",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
    plain: bool = typer.Option(False, "--plain", "-p", help="Plain TSV output (no colors, no borders)"),
    tsv: bool = typer.Option(False, "--tsv", help="Plain TSV output (alias for --plain)"),
    select: Optional[str] = typer.Option(None, "--select", help="Comma-separated field names to show (e.g. 'name,duration')"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would happen without making changes"),
    policy_profile: Optional[str] = typer.Option(
        None,
        "--policy-profile",
        help="Policy profile: read_only|auto_edit",
    ),
    ffmpeg_path: Optional[str] = typer.Option(None, "--ffmpeg-path", help="Absolute path to ffmpeg binary"),
    ffprobe_path: Optional[str] = typer.Option(None, "--ffprobe-path", help="Absolute path to ffprobe binary"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    version: bool = typer.Option(False, "--version", help="Show version"),
):
    """Global options."""
    if output_mode and output_mode not in _OUTPUT_MODES:
        raise typer.BadParameter("Invalid --output-mode. Use one of: json, table, plain, quiet, agent")
    if policy_profile and policy_profile not in {"read_only", "auto_edit"}:
        raise typer.BadParameter("Invalid --policy-profile. Use one of: read_only, auto_edit")

    if output_mode:
        set_output_mode(output_mode)
    elif json_output:
        set_output_mode("json")
    elif agent_output:
        set_output_mode("agent")
    elif quiet:
        set_output_mode("quiet")
    elif plain or tsv:
        set_output_mode("plain")
    else:
        env_mode = _env_default_output_mode()
        if env_mode:
            set_output_mode(env_mode)

    set_lean(bool(lean))

    cfg = get_config()
    configured_profile = policy_profile or cfg.get("security", "policy_profile", "auto_edit")
    try:
        configure_policy(profile=configured_profile)
    except ValidationError as exc:
        raise typer.BadParameter(str(exc))

    if version:
        if output_mode in {"json", "agent"} or json_output or agent_output:
            output({"cli_version": __version__})
        else:
            typer.echo(f"cutagent {__version__}")
        raise typer.Exit()

    if select:
        set_select_fields(select)

    set_dry_run(bool(dry_run))

    if ffmpeg_path:
        set_tool_override("ffmpeg", ffmpeg_path)
    if ffprobe_path:
        set_tool_override("ffprobe", ffprobe_path)

    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)
    set_verbose(verbose)


app.add_typer(project.app, name="project", help="Project management")
app.add_typer(asset.app, name="asset", help="Read-only asset resolution")
app.add_typer(timeline.app, name="timeline", help="Timeline operations")
app.add_typer(media.app, name="media", help="Media Pool operations")
app.add_typer(multicam.app, name="multicam", help="Native multicam primitives and structured jobs")
app.add_typer(storage.app, name="storage", help="Media Storage (disk)")
app.add_typer(clip.app, name="clip", help="Clip / timeline item operations")
app.add_typer(bulk.app, name="bulk", help="Bulk clip operations: select clips by track/name/duration/range and mutate them all in one pass")
app.add_typer(color.app, name="color", help="Color grading")
app.add_typer(render.app, name="render", help="Rendering / delivery")
app.add_typer(burnin.app, name="burnin", help="Burn-in preset operations")
app.add_typer(system.app, name="system", help="DaVinci Resolve system operations")
app.add_typer(page.app, name="page", help="Page navigation")
app.add_typer(fusion.app, name="fusion", help="Fusion operations")
app.add_typer(text.app, name="text", help="Agent-facing text and title operations")
app.add_typer(transcript.app, name="transcript", help="AI transcription in the CutAgent desktop app")
app.add_typer(video.app, name="video", help="AI video generation in the CutAgent desktop app")
app.add_typer(fairlight.app, name="fairlight", help="Fairlight audio")
app.add_typer(edit.app, name="edit", help="Edit operations (blade, insert, trim, transitions, FX)")
app.add_typer(audio.app, name="audio", help="External audio preprocessing helpers (info, duck, reverb)")
app.add_typer(batch.app, name="batch", help="Batch/YAML deterministic recipes")
app.add_typer(auto_edit.app, name="auto-edit", help="One-command auto-edit pipeline")
app.add_typer(embedded.app, name="embedded", help="Connect to DaVinci Resolve 20+ Free")
app.add_typer(version_commands.app, name="version", help="Prompt checkpoints and version history")
app.add_typer(developer.app, name="developer", help="DaVinci Resolve Developer SDK docs and diagnostics")
app.add_typer(workflow.app, name="workflow", help="Workflow Integration SDK helpers")
app.add_typer(script.app, name="script", help="DaVinci Resolve script helpers")
app.add_typer(dctl.app, name="dctl", help="DCTL helpers")
app.add_typer(lut.app, name="lut", help="LUT helpers")
app.add_typer(fuse.app, name="fuse", help="Fusion Fuse helpers")
app.add_typer(ofx.app, name="ofx", help="OpenFX SDK helpers")
app.add_typer(codec.app, name="codec", help="Codec Plugin SDK helpers")

# Top-level utility commands
app.command("status")(utility.status)
app.command("context")(utility.context)
app.command("info")(utility.info)
app.command("connect")(utility.connect)
app.command("product")(utility.product)
app.command("quit")(utility.quit)
app.command("lut-refresh")(utility.lut_refresh)
app.command("doctor")(utility.doctor)
app.command("capabilities")(utility.capabilities)
app.add_typer(utility.layout_app, name="layout", help="Layout preset management")


@app.command("sdk-action-read", hidden=True)
def sdk_action_read(
    action_id: str = typer.Argument(...),
    input_json: str = typer.Option(..., "--input-json"),
) -> None:
    """Execute one generated, read-only SDK descriptor behind the private CLI boundary."""
    from .sdk_low_level_runtime import lower_read_action

    try:
        lowered = lower_read_action(action_id, input_json)
    except ValidationError as exc:
        json_error(code=exc.code, message=str(exc), details=exc.details, suggested_fix=exc.suggested_fix)
        raise typer.Exit(exc.exit_code)
    token = _SDK_READ_DISPATCH.set(True)
    try:
        app(args=["--json", *lowered], prog_name="cutagent", standalone_mode=False)
    finally:
        _SDK_READ_DISPATCH.reset(token)


@app.command("sdk-evaluator-sound-library-observe", hidden=True)
@handle_errors
def sdk_evaluator_sound_library_observe(
    scope: str = typer.Option(..., "--scope"),
    source_root: str = typer.Option(..., "--source-root"),
    phase: str = typer.Option(..., "--phase"),
) -> None:
    """Capture private, read-only Sound Library evidence for the native evaluator."""
    from .sdk_evaluator_sound_library import observe_active_sound_library_database

    set_execution_engine("db_direct")
    result = observe_active_sound_library_database(
        scope=scope,
        source_root=source_root,
        phase=phase,
    )
    output(result, title="SDK Evaluator Sound Library Observation")


@app.command("launch", help="Launch DaVinci Resolve (optionally headless).")
@handle_errors
def launch(
    headless: bool = typer.Option(False, "--headless", help="Launch DaVinci Resolve with -nogui"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait until scripting bridge is reachable"),
    timeout_s: float = typer.Option(60.0, "--timeout-s", help="Wait timeout in seconds"),
    resolve_path: Optional[str] = typer.Option(None, "--resolve-path", help="Path to DaVinci Resolve binary"),
):
    """Launch DaVinci Resolve process."""
    enforce_mutation_policy(
        "system.launch_headless",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        launch_ops.validate_timeout(timeout_s)
        resolved_path = launch_ops.resolve_binary_path(resolve_path) if resolve_path is not None else None
        output(
            {
                "message": "DRY-RUN: would launch DaVinci Resolve.",
                "headless": headless,
                "wait": wait,
                "timeout_s": timeout_s,
                "resolve_path": resolve_path,
                "resolved_path": resolved_path,
                "would_launch": True,
            }
        )
        return
    data = launch_ops.launch_resolve(
        headless=headless,
        wait=wait,
        timeout_s=timeout_s,
        resolve_path=resolve_path,
    )
    output(data, title="Launch")


def _sanitized_excepthook(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
    """Last-resort handler: a packaged build must never print a traceback.

    Diagnostic tracebacks stay available behind --verbose only.
    """
    if "--verbose" in sys.argv[1:] or "-v" in sys.argv[1:]:
        sys.__excepthook__(exc_type, exc, tb)
        return
    if issubclass(exc_type, KeyboardInterrupt):
        print("Interrupted.", file=sys.stderr)
        return
    if is_machine_mode() and not has_response_emitted():
        json_error(
            code="INTERNAL_ERROR",
            message="CutAgent CLI hit an unexpected internal error.",
            details={"type": exc_type.__name__},
        )
    print(
        f"CutAgent CLI: unexpected internal error ({exc_type.__name__}). Re-run with --verbose for diagnostics.",
        file=sys.stderr,
    )


def _configure_windows_utf8_streams() -> None:
    """Keep redirected Windows output Unicode-safe.

    Python can select a legacy Windows code page for redirected stdout/stderr,
    even though the interactive console path supports Unicode. Commands that
    include symbols or non-ASCII project names must still emit complete tables
    and machine envelopes.
    """
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            # Embedded/test streams may be immutable or already finalized.
            continue


def run() -> None:
    """Entry point: run the CLI with sanitized last-resort error handling."""
    _configure_windows_utf8_streams()
    sys.excepthook = _sanitized_excepthook
    if sys.argv[1:] == ["--cutagent-internal-sdk-prepared-action-host"]:
        if os.environ.pop("CUTAGENT_INTERNAL_PREPARED_ACTION_HOST", None) != "1":
            raise SystemExit(2)
        from .prepared_action_host import run_prepared_action_host

        run_prepared_action_host()
        return
    try:
        app()
    except KeyboardInterrupt:
        # Interrupts can arrive while Click is still importing command modules,
        # loading the command catalog, or parsing root options. Those phases run
        # outside the per-command ``@handle_errors`` boundary, so catch them at
        # the console entry point as well and never let the Python launcher emit
        # a traceback.
        machine_mode = _requested_machine_mode(sys.argv[1:])
        if machine_mode is not None:
            set_output_mode(machine_mode)
            set_command_context(infer_canonical_command_id(sys.argv[1:]))
            if not has_response_emitted():
                json_error(
                    code="INTERNAL_ERROR",
                    message="Interrupted.",
                    details={"type": "KeyboardInterrupt"},
                )
        else:
            print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    run()
