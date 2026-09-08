"""Embedded DaVinci Resolve 20+ Free localhost bridge support.

The embedded transport keeps DaVinci Resolve operations flowing through CutAgent CLI while
letting a Lua script running inside DaVinci Resolve 20+ Free execute the actual API
calls.  Python CLI commands talk to a small localhost broker; CutAgent.lua keeps
a persistent connection to that broker from inside DaVinci Resolve.
"""

from __future__ import annotations

import asyncio
import atexit
import base64
import errno
import hashlib
import ipaddress
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from . import __version__
from .local_admission import authorization_required, infer_current_command_id, verify_authorization_token
from .errors import (
    APICallFailed,
    EmbeddedBridgeAuthFailed,
    EmbeddedBridgeNotRunning,
    EmbeddedBridgeOutdated,
    EmbeddedBridgeTimeout,
    ValidationError,
)

EMBEDDED_PROTOCOL_VERSION = 4
EMBEDDED_BRIDGE_VERSION = "1.3.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18764
SCRIPT_NAME = "DaVinciResolveSDK.lua"
LEGACY_AUTOSTART_SCRIPT_NAME = "DaVinciResolveSDK.scriptlib"
AUTH_FILE_NAME = "embedded-bridge-auth.json"
FOCUS_DEEP_LINK = ""
WINDOWS_SOCKET_TRANSPORT_ASSET = "windows-luasocket/socket.dll"
WINDOWS_SOCKET_TRANSPORT_NAME = "socket.dll"
HTTP_POLL_TIMEOUT_SECONDS = 25.0
HTTP_CONNECTED_TTL_SECONDS = HTTP_POLL_TIMEOUT_SECONDS + 10.0
SPOOL_CONNECTED_TTL_SECONDS = 10.0
SPOOL_ACCEPT_TIMEOUT_SECONDS = 3.0
SPOOL_POLL_INTERVAL_SECONDS = 0.05
SPOOL_AUTH_CONFIG_NAME = "auth.lua"
SPOOL_REQUEST_NAME = "request.lua"
SPOOL_RESPONSE_NAME = "response.prefs"
SPOOL_RESPONSE_KEY = "DaVinciResolveSdkEmbeddedResponse"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 300.0
REQUEST_TIMEOUT_ENV = "DAVINCI_RESOLVE_SDK_EMBEDDED_REQUEST_TIMEOUT_S"
CLIENT_LOCAL_PORT_START = 18200
CLIENT_LOCAL_PORT_END = 18399


def _embedded_script_host_pids(home: Path | None = None) -> list[int]:
    """Return macOS fuscript hosts running CutAgent's installed utility script."""
    if sys.platform != "darwin":
        return []
    script_paths = {
        str(script_install_path(home, sandbox=False)),
        str(script_install_path(home, sandbox=True)),
    }
    try:
        completed = subprocess.run(
            ["/bin/ps", "-ww", "-axo", "pid=,ucomm=,args="],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []

    pids: list[int] = []
    for line in completed.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        pid_text, process_name, command = parts
        if process_name != "fuscript":
            continue
        if not any(command == path or command.endswith(f" {path}") for path in script_paths):
            continue
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if pid > 0 and pid != os.getpid():
            pids.append(pid)
    return sorted(set(pids))


def terminate_embedded_script_hosts(home: Path | None = None) -> dict[str, Any]:
    """Stop orphanable macOS fuscript hosts after DaVinci Resolve exits."""
    matched = _embedded_script_host_pids(home)
    if not matched:
        return {"matched": 0, "terminated": 0, "remaining": 0}

    for pid in matched:
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    deadline = time.monotonic() + 2.0
    remaining = sorted(set(matched) & set(_embedded_script_host_pids(home)))
    while remaining and time.monotonic() < deadline:
        time.sleep(0.05)
        remaining = sorted(set(matched) & set(_embedded_script_host_pids(home)))

    # Resolve:Quit() can leave fuscript blocked inside the native API call, so
    # a graceful signal is not always sufficient. Revalidate the exact command
    # before escalating; never target unrelated fuscript sessions.
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass

    kill_deadline = time.monotonic() + 1.0
    remaining = sorted(set(matched) & set(_embedded_script_host_pids(home)))
    while remaining and time.monotonic() < kill_deadline:
        time.sleep(0.05)
        remaining = sorted(set(matched) & set(_embedded_script_host_pids(home)))

    return {
        "matched": len(matched),
        "terminated": len(matched) - len(remaining),
        "remaining": len(remaining),
    }


def embedded_request_timeout_seconds(default: float = DEFAULT_REQUEST_TIMEOUT_SECONDS) -> float:
    raw = os.environ.get(REQUEST_TIMEOUT_ENV, "").strip()
    if not raw:
        return float(default)
    try:
        timeout = float(raw)
    except (TypeError, ValueError):
        return float(default)
    if timeout <= 0:
        return float(default)
    return timeout


_TIMEOUT_DIAGNOSTIC_HINT = (
    "The embedded Lua bridge is connected, but DaVinci Resolve did not return from the API call before the timeout. "
    "If DaVinci Resolve shows a modal dialog or a macOS file-access prompt, approve or dismiss it and retry. "
    "For output/import paths under Desktop, Documents, Downloads, removable drives, or network volumes, grant "
    "DaVinci Resolve access to that location or use an already authorized export folder."
)


def _embedded_timeout_details(
    *,
    method: str,
    params: dict[str, Any] | None,
    timeout_s: float,
    host: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "timeout_s": timeout_s,
        "bridge_method": method or None,
        "diagnostic_hint": _TIMEOUT_DIAGNOSTIC_HINT,
        "possible_blockers": [
            "long_running_resolve_operation",
            "resolve_modal_dialog",
            "macos_protected_folder_permission_prompt",
        ],
    }
    if host is not None:
        details["host"] = host
    if port is not None:
        details["port"] = port
    if not isinstance(params, dict):
        return details

    op = params.get("op")
    resolve_method = params.get("method")
    target = params.get("target")
    if isinstance(op, str) and op:
        details["op"] = op
    if isinstance(resolve_method, str) and resolve_method:
        details["resolve_method"] = resolve_method
    if isinstance(target, str) and target:
        details["target"] = target
    return details


READ_ONLY_RESOLVE_METHODS = frozenset(
    {
        "FindTool",
        "Fusion",
        "GetAttrs",
        "GetAudioMapping",
        "GetAudioSamples",
        "GetAudioWaveform",
        "GetCDL",
        "GetClipColor",
        "GetClipList",
        "GetClipProperty",
        "GetConnectedOutput",
        "GetCurrentComp",
        "GetCurrentDatabase",
        "GetCurrentFolder",
        "GetCurrentPage",
        "GetCurrentProject",
        "GetCurrentRenderFormatAndCodec",
        "GetCurrentRenderMode",
        "GetCurrentTimecode",
        "GetCurrentTimeline",
        "GetCurrentVideoItem",
        "GetDatabaseList",
        "GetDuration",
        "GetEnd",
        "GetEndTimecode",
        "GetFairlightPresets",
        "GetFairlightRecordSettings",
        "GetFileList",
        "GetFlagList",
        "GetFolderListInCurrentFolder",
        "GetFusionCompByIndex",
        "GetFusionCompByName",
        "GetFusionCompCount",
        "GetGalleryStillAlbums",
        "GetInput",
        "GetInputList",
        "GetIOPatch",
        "GetIsTrackEnabled",
        "GetIsTrackLocked",
        "GetClipEnabled",
        "GetColorGroup",
        "GetCurrentVersion",
        "GetCurrentVersionName",
        "GetIsColorOutputCacheEnabled",
        "GetIsFusionOutputCacheEnabled",
        "GetItemListInTrack",
        "GetKeyFrames",
        "GetKeyframeAtIndex",
        "GetKeyframeCount",
        "GetLabel",
        "GetLeftOffset",
        "GetLUT",
        "GetLinkedItems",
        "GetRegList",
        "GetMarkers",
        "GetMediaPool",
        "GetMediaPoolItem",
        "GetMediaStorage",
        "GetMetadata",
        "GetMountedVolumeList",
        "GetName",
        "GetNodeGraph",
        "GetNodeLabel",
        "GetNumNodes",
        "GetOutputList",
        "GetPatchInput",
        "GetPatchIO",
        "GetProductName",
        "GetProjectListInCurrentFolder",
        "GetProjectManager",
        "GetProperty",
        "GetPropertyAtKeyframeIndex",
        "GetRenderJobList",
        "GetRenderJobStatus",
        "GetRenderCodecs",
        "GetRenderFormats",
        "GetRenderSettings",
        "GetRightOffset",
        "GetRootFolder",
        "GetSelectedTakeIndex",
        "GetSetting",
        "GetSourceAudioChannelMapping",
        "GetStart",
        "GetStartFrame",
        "GetStartTimecode",
        "GetStills",
        "GetSubFolderList",
        "GetTakeByIndex",
        "GetTakesCount",
        "GetTimelineByIndex",
        "GetTimelineCount",
        "GetTool",
        "GetToolList",
        "GetToolsInNode",
        "GetTrackCount",
        "GetTrackFolderCollapsed",
        "GetTrackFolderInfo",
        "GetTrackFolderList",
        "GetTrackFolderMembership",
        "GetTrackFolders",
        "GetTrackName",
        "GetTrackSubType",
        "GetTrackTypeAndIndex",
        "GetUniqueId",
        "GetVersion",
        "GetVersionNameList",
        "GetVersionString",
        "GetVoiceIsolationState",
        "IsRendering",
        "IsRenderingInProgress",
        # Read-only Fairlight probe candidates. These are intentionally not
        # classified as implementation support until DaVinci Resolve returns a real API
        # result and the command layer has readback coverage.
        "GetADRCueList",
        "GetADRCues",
        "GetADRSettings",
        "GetADRTakes",
        "GetAudioEffects",
        "GetAudioMeterData",
        "GetAudioMeters",
        "GetAudioTransitionList",
        "GetAudioTransitions",
        "GetBusEffects",
        "GetBusList",
        "GetBusPluginList",
        "GetBusRouting",
        "GetClipEQ",
        "GetClipEQSettings",
        "GetClipEffects",
        "GetDialogLevelerState",
        "GetDialogueLeveler",
        "GetDialogueLevelerState",
        "GetElasticAudio",
        "GetElasticWaveItems",
        "GetElasticWaveKeyframes",
        "GetElasticWaveState",
        "GetExternalAudioProcesses",
        "GetFairlightExternalProcesses",
        "GetFairlightBuses",
        "GetFairlightEffectList",
        "GetFairlightEffects",
        "GetFairlightGroups",
        "GetFairlightMeter",
        "GetFairlightMonitorSettings",
        "GetFairlightPlugInList",
        "GetFairlightPluginList",
        "GetFairlightSends",
        "GetFairlightVCAs",
        "GetFlexBusGraph",
        "GetGroupList",
        "GetIntegratedLoudness",
        "GetLoudnessAnalysis",
        "GetLoudnessInfo",
        "GetLoudnessReport",
        "GetMixerMeters",
        "GetMonitorLevel",
        "GetMonitorMute",
        "GetMonitorSettings",
        "GetMusicRemixer",
        "GetMusicRemixerState",
        "GetRetimeProcess",
        "GetSampleRepairState",
        "GetSendList",
        "GetSoundLibrary",
        "GetSoundLibraryAuditionState",
        "GetSoundLibraryItems",
        "GetSoundLibraryPreviewState",
        "GetControlRoomLevel",
        "GetControlRoomMute",
        "GetTrackArmForRecord",
        "GetTrackColor",
        "GetTrackEffects",
        "GetTrackGroup",
        "GetTrackHeight",
        "GetTrackInputMonitor",
        "GetTrackInputMonitoring",
        "GetTrackMeter",
        "GetTrackMeters",
        "GetTrackPluginList",
        "GetTrackPluginParameters",
        "GetTrackAutomation",
        "GetTrackRecordEnable",
        "GetTrackFormat",
        "GetTrackSendList",
        "GetTrackSends",
        "GetTrackProcessing",
        "GetTrackProperties",
        "GetTrackRouting",
        "GetTrackVCA",
        "GetTrackVisibility",
        "GetTrackVisible",
        "GetTruePeak",
        "GetVCAList",
        "GetWaveform",
        "GetWaveformData",
    }
)

MUTATING_RESOLVE_METHODS = frozenset(
    {
        "AddFlag",
        "AddFusionComp",
        "AddItemListToMediaPool",
        "AddKeyframe",
        "AddMarker",
        "AddSubFolder",
        "AddTool",
        "AddTrack",
        "AddVersion",
        "AppendToTimeline",
        "ApplyFairlightPresetToCurrentTimeline",
        "ApplyFairlightPreset",
        "ApplyGrade",
        "ApplyGradeFromDRX",
        "ArchiveProject",
        "ClearClipColor",
        "ClearFlags",
        "CloseProject",
        "ConnectTo",
        "Copy",
        "CopyGrades",
        "CreateEmptyTimeline",
        "CreateFolder",
        "CreateProject",
        "CreateTimelineFromClips",
        "DeleteClips",
        "DeleteTrack",
        "Delete",
        "DeleteMarkerAtFrame",
        "DeleteMarkersByColor",
        "DeleteAllRenderJobs",
        "DeleteProject",
        "DeleteRenderJob",
        "DeleteTimelines",
        "DeleteVersionByName",
        "ExportCurrentFrameAsStill",
        "Export",
        "ExportFusionComp",
        "ExportProject",
        "ExportToFile",
        "GotoParentFolder",
        "GrabStill",
        "ImportFusionComp",
        "ImportMedia",
        "ImportProject",
        "ImportTimelineFromFile",
        "InsertAudioToCurrentTrackAtPlayhead",
        "LoadProject",
        "LoadVersionByName",
        "MoveClips",
        "OpenFolder",
        "OpenPage",
        "Paste",
        "Play",
        "Quit",
        "RefreshLUTList",
        "Render",
        "RestoreProject",
        "SaveAsNewRenderPreset",
        "SaveProject",
        "AddRenderJob",
        "SetActiveTool",
        "SetAttrs",
        "SetCDL",
        "SetClipColor",
        "SetClipsLinked",
        "SetClipProperty",
        "SetCurrentDatabase",
        "SetCurrentFolder",
        "SetCurrentRenderFormatAndCodec",
        "SetCurrentRenderMode",
        "SetCurrentTimecode",
        "SetCurrentTimeline",
        "SetInput",
        "SetLUT",
        "SetMetadata",
        "SetName",
        "SetProperty",
        "SetRenderSettings",
        "SetSetting",
        "SetColorOutputCache",
        "SetClipEnabled",
        "SetFusionOutputCache",
        "SetTrackColor",
        "SetTrackEnable",
        "SetTrackLock",
        "SetTrackName",
        "SetVoiceIsolationState",
        "StartRendering",
        "Stabilize",
        "Stop",
        "StopRendering",
        "SmartReframe",
    }
)

DESTRUCTIVE_RESOLVE_METHODS = frozenset(
    {
        "ArchiveProject",
        "ClearFlags",
        "CloseProject",
        "Delete",
        "DeleteClips",
        "DeleteMarkerAtFrame",
        "DeleteMarkersByColor",
        "DeleteAllRenderJobs",
        "DeleteProject",
        "DeleteRenderJob",
        "DeleteTrack",
        "DeleteTimelines",
        "DeleteVersionByName",
        "Quit",
        "RestoreProject",
        "SetCurrentDatabase",
        "StopRendering",
    }
)

SUPPORTED_RESOLVE_METHODS = READ_ONLY_RESOLVE_METHODS | MUTATING_RESOLVE_METHODS


def embedded_host() -> str:
    raw = os.environ.get("DAVINCI_RESOLVE_SDK_EMBEDDED_HOST", DEFAULT_HOST)
    host = raw.strip() if isinstance(raw, str) else DEFAULT_HOST
    if not host:
        return DEFAULT_HOST
    if host.lower() in {"localhost", "localhost."}:
        return "localhost"
    address_input = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        address = ipaddress.ip_address(address_input)
    except ValueError as exc:
        raise ValueError("DAVINCI_RESOLVE_SDK_EMBEDDED_HOST must be a loopback host or IP address.") from exc
    if not address.is_loopback:
        raise ValueError("DAVINCI_RESOLVE_SDK_EMBEDDED_HOST must be a loopback host or IP address.")
    return address.compressed


def embedded_port() -> int:
    raw = os.environ.get("DAVINCI_RESOLVE_SDK_EMBEDDED_PORT")
    if raw:
        try:
            value = int(raw)
            if 0 < value < 65536:
                return value
        except ValueError:
            pass
    return DEFAULT_PORT


def _sanitize_embedded_auth_scope(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    chars: list[str] = []
    for char in raw:
        if ("a" <= char <= "z") or ("0" <= char <= "9") or char in {"_", "-", "."}:
            chars.append(char)
        else:
            chars.append("-")
    normalized = "".join(chars).strip("._-")
    return normalized or "local"


def embedded_auth_scope(*args, **kwargs):
    return "standalone"


def embedded_auth_path(home: Path | None = None) -> Path:
    override = os.environ.get("DAVINCI_RESOLVE_SDK_EMBEDDED_AUTH_PATH")
    if override:
        return Path(override).expanduser()
    root = _cutagent_app_support_dir(home)
    scope = embedded_auth_scope()
    scoped_name = f"{AUTH_FILE_NAME[:-5]}.{scope}.json"
    return root / scoped_name


def _windows_roaming_appdata_dir(home: Path | None = None) -> Path:
    if home is not None:
        return home / "AppData" / "Roaming"
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        return Path(appdata)
    return Path.home() / "AppData" / "Roaming"


def _cutagent_app_support_dir(home: Path | None = None) -> Path:
    if sys.platform == "win32":
        return _windows_roaming_appdata_dir(home) / "DaVinciResolveSDK"
    root = home or Path.home()
    return root / "Library" / "Application Support" / "DaVinciResolveSDK"


def embedded_spool_dir(*, home: Path | None = None, auth_path: Path | None = None) -> Path:
    path = auth_path or embedded_auth_path(home)
    return path.parent / f"{path.name}.spool"


def embedded_spool_paths(*, home: Path | None = None, auth_path: Path | None = None) -> dict[str, Path]:
    root = embedded_spool_dir(home=home, auth_path=auth_path)
    return {
        "root": root,
        "auth": root / SPOOL_AUTH_CONFIG_NAME,
        "request": root / SPOOL_REQUEST_NAME,
        "response": root / SPOOL_RESPONSE_NAME,
    }


def _write_private_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _lua_base64_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=_json_default).encode("utf-8")
    return f'return "{base64.b64encode(encoded).decode("ascii")}"\n'


def write_embedded_spool_payload(path: Path, payload: dict[str, Any]) -> None:
    _write_private_text(path, _lua_base64_payload(payload))


_SPOOL_RESPONSE_PATTERN = re.compile(
    rf"\b{re.escape(SPOOL_RESPONSE_KEY)}\s*=\s*\"([A-Za-z0-9+/]*={{0,2}})\""
)


def read_embedded_spool_response(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return None
    # Fusion's SavePrefs replaces the response file and applies the Resolve
    # process umask, even when the broker pre-created the path as 0600.  The
    # enclosing spool directory is already 0700; restore the file mode as soon
    # as the broker observes each replacement so copied/relaxed directories do
    # not turn authenticated response payloads into a readable artifact.
    try:
        path.chmod(0o600)
    except OSError:
        pass
    match = _SPOOL_RESPONSE_PATTERN.search(text)
    if not match:
        return None
    try:
        decoded = base64.b64decode(match.group(1), validate=True).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _resolve_app_support_dir(home: Path | None = None) -> Path:
    if sys.platform == "win32":
        return _windows_roaming_appdata_dir(home) / "Blackmagic Design" / "DaVinci Resolve" / "Support"
    root = home or Path.home()
    return root / "Library" / "Application Support" / "Blackmagic Design" / "DaVinci Resolve"


def read_embedded_auth_config(*, home: Path | None = None) -> dict[str, Any]:
    path = embedded_auth_path(home)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _valid_loopback_host(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    host = value.strip()
    if not host:
        return None
    if host.lower() in {"localhost", "localhost."}:
        return "localhost"
    address_input = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        address = ipaddress.ip_address(address_input)
    except ValueError:
        return None
    return address.compressed if address.is_loopback else None


def _valid_port(value: Any) -> int | None:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    return port if 0 < port < 65536 else None


def read_embedded_auth_token(*, home: Path | None = None) -> str | None:
    env_token = os.environ.get("DAVINCI_RESOLVE_SDK_EMBEDDED_AUTH_TOKEN", "").strip()
    if env_token:
        return env_token
    payload = read_embedded_auth_config(home=home)
    token = payload.get("auth_token")
    return token if isinstance(token, str) and token else None


def embedded_auth_token_status(*, home: Path | None = None, auth_path: Path | None = None) -> dict[str, Any]:
    path = auth_path or embedded_auth_path(home)
    status: dict[str, Any] = {
        "auth_path": str(path),
        "auth_token_present": False,
        "auth_token_valid": False,
        "auth_token_readable": False,
    }
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        status["error"] = "missing"
        return status
    except OSError as exc:
        status["error"] = str(exc)
        return status

    status["auth_token_readable"] = True
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        status["error"] = "invalid_json"
        return status

    if not isinstance(payload, dict):
        status["error"] = "invalid_payload"
        return status

    token = payload.get("auth_token")
    status["auth_token_present"] = isinstance(token, str) and bool(token)
    status["auth_token_valid"] = status["auth_token_present"]
    for key in ("host", "port", "bridge_version", "protocol_version", "created_at"):
        value = payload.get(key)
        if isinstance(value, (str, int, float)):
            status[key] = value
    if not status["auth_token_valid"]:
        status["error"] = "missing_auth_token"
    return status


def write_embedded_auth_token(
    token: str,
    *,
    host: str,
    port: int,
    auth_path: Path | None = None,
) -> Path:
    path = auth_path or embedded_auth_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    payload = {
        "auth_token": token,
        "host": host,
        "port": port,
        "bridge_version": EMBEDDED_BRIDGE_VERSION,
        "protocol_version": EMBEDDED_PROTOCOL_VERSION,
        "created_at": time.time(),
    }
    desktop_focus = _desktop_focus_config_from_env()
    if desktop_focus:
        payload["desktop_focus"] = desktop_focus
    encoded = json.dumps(payload, separators=(",", ":"), default=_json_default)
    _write_private_text(path, encoded)
    spool_paths = embedded_spool_paths(auth_path=path)
    write_embedded_spool_payload(spool_paths["auth"], payload)
    try:
        spool_paths["request"].unlink()
    except FileNotFoundError:
        pass
    # Fusion's SavePrefs otherwise creates this file using the process umask
    # (commonly 0666). Pre-creating it keeps the response private even if the
    # spool directory is copied or its permissions are changed later.
    _write_private_text(spool_paths["response"], "")
    return path


def _desktop_focus_config_from_env(*args, **kwargs):
    return None


def remove_embedded_auth_token(token: str, *, auth_path: Path | None = None) -> None:
    path = auth_path or embedded_auth_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(payload, dict) and payload.get("auth_token") == token:
        try:
            path.unlink()
        except OSError:
            pass
        spool_paths = embedded_spool_paths(auth_path=path)
        for item in (spool_paths["auth"], spool_paths["request"], spool_paths["response"]):
            try:
                item.unlink()
            except OSError:
                pass
        try:
            spool_paths["root"].rmdir()
        except OSError:
            pass


def utility_scripts_dir(home: Path | None = None) -> Path:
    return (
        _resolve_app_support_dir(home)
        / "Fusion"
        / "Scripts"
        / "Utility"
    )


def sandbox_utility_scripts_dir(home: Path | None = None) -> Path:
    if sys.platform == "win32":
        return utility_scripts_dir(home)
    root = home or Path.home()
    return (
        root
        / "Library"
        / "Containers"
        / "com.blackmagic-design.DaVinciResolveAppStore"
        / "Data"
        / "Library"
        / "Application Support"
        / "Blackmagic Design"
        / "DaVinci Resolve"
        / "Fusion"
        / "Scripts"
        / "Utility"
    )


def script_install_path(home: Path | None = None, *, sandbox: bool = False) -> Path:
    base = sandbox_utility_scripts_dir(home) if sandbox else utility_scripts_dir(home)
    return base / SCRIPT_NAME


def legacy_autostart_script_install_path(home: Path | None = None, *, sandbox: bool = False) -> Path:
    """Return the retired global script-library path so installs can remove it."""
    return script_install_path(home, sandbox=sandbox).parent.parent / LEGACY_AUTOSTART_SCRIPT_NAME


def script_source_text() -> str:
    text = resources.files("cutagent_cli.assets").joinpath(SCRIPT_NAME).read_text(encoding="utf-8")
    spool_paths = embedded_spool_paths()
    return (
        text.replace("__CUTAGENT_PROTOCOL_VERSION__", str(EMBEDDED_PROTOCOL_VERSION))
        .replace("__CUTAGENT_BRIDGE_VERSION__", lua_quoted_string_content(EMBEDDED_BRIDGE_VERSION))
        .replace("__CUTAGENT_DEFAULT_HOST__", lua_quoted_string_content(embedded_host()))
        .replace("__CUTAGENT_DEFAULT_PORT__", str(embedded_port()))
        .replace("__CUTAGENT_AUTH_PATH__", lua_quoted_string_content(str(embedded_auth_path())))
        .replace("__CUTAGENT_SPOOL_AUTH_PATH__", lua_quoted_string_content(str(spool_paths["auth"])))
        .replace("__CUTAGENT_SPOOL_REQUEST_PATH__", lua_quoted_string_content(str(spool_paths["request"])))
        .replace("__CUTAGENT_SPOOL_RESPONSE_PATH__", lua_quoted_string_content(str(spool_paths["response"])))
        .replace("__CUTAGENT_SPOOL_RESPONSE_KEY__", lua_quoted_string_content(SPOOL_RESPONSE_KEY))
    )


def lua_quoted_string_content(value: str) -> str:
    escaped: list[str] = []
    for char in str(value):
        codepoint = ord(char)
        if char == "\\":
            escaped.append("\\\\")
        elif char == '"':
            escaped.append('\\"')
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\r":
            escaped.append("\\r")
        elif char == "\t":
            escaped.append("\\t")
        elif codepoint < 32:
            escaped.append(f"\\{codepoint:03d}")
        else:
            escaped.append(char)
    return "".join(escaped)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lua_modules_dir(home: Path | None = None) -> Path:
    return _resolve_app_support_dir(home) / "Fusion" / "Modules" / "Lua"


def windows_socket_transport_install_path(home: Path | None = None) -> Path:
    return lua_modules_dir(home) / WINDOWS_SOCKET_TRANSPORT_NAME


def windows_socket_transport_asset_bytes() -> bytes | None:
    try:
        return resources.files("cutagent_cli.assets").joinpath(
            *WINDOWS_SOCKET_TRANSPORT_ASSET.split("/")
        ).read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return None


def windows_socket_transport_status(home: Path | None = None) -> dict[str, Any]:
    path = windows_socket_transport_install_path(home)
    asset = windows_socket_transport_asset_bytes()
    asset_hash = sha256_bytes(asset) if asset is not None else None
    installed_hash = None
    installed = path.is_file()
    if installed:
        try:
            installed_hash = sha256_bytes(path.read_bytes())
        except OSError:
            installed_hash = None
    return {
        "applicable": sys.platform == "win32",
        "name": WINDOWS_SOCKET_TRANSPORT_NAME,
        "path": str(path),
        "asset": WINDOWS_SOCKET_TRANSPORT_ASSET,
        "asset_available": asset is not None,
        "asset_hash": asset_hash,
        "installed": installed,
        "hash": installed_hash,
        "current": bool(asset_hash and installed_hash and installed_hash == asset_hash),
    }


def install_windows_socket_transport(home: Path | None = None) -> dict[str, Any]:
    status = windows_socket_transport_status(home)
    if sys.platform != "win32":
        return {**status, "installed": False, "updated": False, "created": False}
    asset = windows_socket_transport_asset_bytes()
    if asset is None:
        return {
            **status,
            "installed": False,
            "updated": False,
            "created": False,
            "error": "missing_windows_socket_transport_asset",
        }
    path = windows_socket_transport_install_path(home)
    previous_hash = status.get("hash")
    next_hash = sha256_bytes(asset)
    changed = previous_hash != next_hash
    path.parent.mkdir(parents=True, exist_ok=True)
    if changed:
        try:
            path.write_bytes(asset)
        except PermissionError as exc:
            raise EmbeddedBridgeOutdated(
                "DaVinci Resolve is using an older CutAgent Windows socket transport. Close DaVinci Resolve, retry the install, then reopen it.",
                details={
                    "reason": "windows_socket_transport_locked",
                    "path": str(path),
                    "restart_required": True,
                    "installed_hash": previous_hash,
                    "required_hash": next_hash,
                },
                recoverability="manual",
                suggested_fix="Close DaVinci Resolve, run `cutagent embedded install` again, then reopen DaVinci Resolve and run Workspace > Scripts > CutAgent.",
            ) from exc
    return {
        **windows_socket_transport_status(home),
        "installed": True,
        "updated": changed and previous_hash is not None,
        "created": changed and previous_hash is None,
    }


def plan_install_windows_socket_transport(home: Path | None = None) -> dict[str, Any]:
    status = windows_socket_transport_status(home)
    changed = bool(status["asset_hash"] and status["hash"] != status["asset_hash"])
    return {
        **status,
        "would_install": sys.platform == "win32",
        "would_update": bool(changed and status["hash"] is not None),
        "would_create": bool(changed and status["hash"] is None),
    }


def uninstall_windows_socket_transport(home: Path | None = None) -> dict[str, Any]:
    path = windows_socket_transport_install_path(home)
    existed = path.is_file()
    if sys.platform == "win32" and existed:
        path.unlink()
    return {
        "applicable": sys.platform == "win32",
        "removed": bool(sys.platform == "win32" and existed),
        "path": str(path),
    }


def request_cutagent_focus_from_embedded_script(*args, **kwargs):
    return False


def installed_script_status(home: Path | None = None) -> dict[str, Any]:
    source = script_source_text()
    source_hash = sha256_text(source)
    candidates = [
        {"kind": "standard", "path": script_install_path(home, sandbox=False)},
        {"kind": "app_store_sandbox", "path": script_install_path(home, sandbox=True)},
    ]
    paths = []
    seen_paths: set[str] = set()
    for item in candidates:
        normalized = str(item["path"])
        if normalized in seen_paths:
            continue
        seen_paths.add(normalized)
        paths.append(item)
    installs = []
    for item in paths:
        path = item["path"]
        exists = path.is_file()
        current_hash = None
        if exists:
            try:
                current_hash = sha256_text(path.read_text(encoding="utf-8"))
            except OSError:
                current_hash = None
        installs.append(
            {
                "kind": item["kind"],
                "path": str(path),
                "installed": exists,
                "hash": current_hash,
                "current": bool(current_hash and current_hash == source_hash),
            }
        )
    legacy_autostart_installs = []
    for item in paths:
        path = legacy_autostart_script_install_path(home, sandbox=item["kind"] == "app_store_sandbox")
        exists = path.is_file()
        legacy_autostart_installs.append(
            {
                "kind": item["kind"],
                "path": str(path),
                "installed": exists,
            }
        )
    return {
        "script_name": SCRIPT_NAME,
        "version": EMBEDDED_BRIDGE_VERSION,
        "protocol_version": EMBEDDED_PROTOCOL_VERSION,
        "source_hash": source_hash,
        "installed": any(item["installed"] for item in installs),
        "current": any(item["current"] for item in installs),
        "installs": installs,
        "legacy_autostart": {
            "script_name": LEGACY_AUTOSTART_SCRIPT_NAME,
            "installed": any(item["installed"] for item in legacy_autostart_installs),
            "installs": legacy_autostart_installs,
        },
        "windows_socket_transport": windows_socket_transport_status(home),
    }


def install_script(home: Path | None = None, *, sandbox: bool = False) -> dict[str, Any]:
    source = script_source_text()
    path = script_install_path(home, sandbox=sandbox)
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_hash = None
    if path.is_file():
        previous_hash = sha256_text(path.read_text(encoding="utf-8"))
    next_hash = sha256_text(source)
    changed = previous_hash != next_hash
    if changed:
        path.write_text(source, encoding="utf-8")
    legacy_autostart_path = legacy_autostart_script_install_path(home, sandbox=sandbox)
    legacy_autostart_removed = legacy_autostart_path.is_file()
    if legacy_autostart_removed:
        legacy_autostart_path.unlink()
    return {
        "installed": True,
        "updated": changed and previous_hash is not None,
        "created": changed and previous_hash is None,
        "path": str(path),
        "legacy_autostart": {
            "path": str(legacy_autostart_path),
            "removed": legacy_autostart_removed,
        },
        "windows_socket_transport": install_windows_socket_transport(home),
        "version": EMBEDDED_BRIDGE_VERSION,
        "protocol_version": EMBEDDED_PROTOCOL_VERSION,
        "hash": next_hash,
        "sandbox": sandbox,
    }


def plan_install_script(home: Path | None = None, *, sandbox: bool = False) -> dict[str, Any]:
    """Return the prospective install result without creating directories or writing files."""
    source = script_source_text()
    path = script_install_path(home, sandbox=sandbox)
    previous_hash = None
    exists = path.is_file()
    if exists:
        try:
            previous_hash = sha256_text(path.read_text(encoding="utf-8"))
        except OSError:
            previous_hash = None
    next_hash = sha256_text(source)
    changed = previous_hash != next_hash
    legacy_autostart_path = legacy_autostart_script_install_path(home, sandbox=sandbox)
    return {
        "installed": exists,
        "updated": False,
        "created": False,
        "would_install": True,
        "would_update": bool(changed and previous_hash is not None),
        "would_create": bool(changed and previous_hash is None),
        "path": str(path),
        "legacy_autostart": {
            "path": str(legacy_autostart_path),
            "would_remove": legacy_autostart_path.is_file(),
        },
        "windows_socket_transport": plan_install_windows_socket_transport(home),
        "version": EMBEDDED_BRIDGE_VERSION,
        "protocol_version": EMBEDDED_PROTOCOL_VERSION,
        "hash": next_hash,
        "previous_hash": previous_hash,
        "sandbox": sandbox,
    }


def uninstall_script(home: Path | None = None, *, sandbox: bool = False) -> dict[str, Any]:
    path = script_install_path(home, sandbox=sandbox)
    existed = path.is_file()
    if existed:
        path.unlink()
    legacy_autostart_path = legacy_autostart_script_install_path(home, sandbox=sandbox)
    legacy_autostart_existed = legacy_autostart_path.is_file()
    if legacy_autostart_existed:
        legacy_autostart_path.unlink()
    return {
        "removed": existed,
        "path": str(path),
        "legacy_autostart": {
            "removed": legacy_autostart_existed,
            "path": str(legacy_autostart_path),
        },
        "sandbox": sandbox,
        "windows_socket_transport": uninstall_windows_socket_transport(home),
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _dumps(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=_json_default) + "\n"
    ).encode("utf-8")


def _loads(line: bytes | str) -> dict[str, Any]:
    text = line.decode("utf-8") if isinstance(line, bytes) else line
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("bridge payload must be a JSON object")
    return payload


def _connect_with_reserved_loopback_source_port(host: str, port: int, timeout: float) -> socket.socket:
    last_error: OSError | None = None
    for local_port in range(CLIENT_LOCAL_PORT_START, CLIENT_LOCAL_PORT_END + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(timeout)
            sock.bind((DEFAULT_HOST, local_port))
            sock.connect((host, port))
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
    if last_error:
        raise last_error
    raise OSError("No reserved loopback source ports are available.")


def create_embedded_client_connection(host: str, port: int, timeout: float) -> socket.socket:
    try:
        return socket.create_connection((host, port), timeout=timeout)
    except OSError as exc:
        if exc.errno not in {errno.EADDRNOTAVAIL, errno.EADDRINUSE}:
            raise
        return _connect_with_reserved_loopback_source_port(host, port, timeout)


def _canonical_embedded_execute_payload(params: dict[str, Any]) -> dict[str, Any]:
    op = params.get("op")
    if op == "call":
        args = params.get("args")
        return {
            "op": "call",
            "target": params.get("target"),
            "method": params.get("method"),
            "args": args if isinstance(args, list) else [],
        }
    return {"op": op}


def canonicalize_embedded_execute_params(params: dict[str, Any]) -> str:
    return json.dumps(
        _canonical_embedded_execute_payload(params if isinstance(params, dict) else {}),
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
        default=_json_default,
    )


def hash_embedded_execute_params(params: dict[str, Any]) -> str:
    return hashlib.sha256(canonicalize_embedded_execute_params(params).encode("utf-8")).hexdigest()


def _execute_params_require_command_auth(params: dict[str, Any] | None) -> bool:
    if not isinstance(params, dict):
        return False
    return params.get("op") == "call" and params.get("method") in MUTATING_RESOLVE_METHODS


@dataclass
class EmbeddedServerStatus:
    running: bool
    connected: bool = False
    client: dict[str, Any] | None = None
    error: str | None = None

    def as_dict(self, *, host: str | None = None, port: int | None = None) -> dict[str, Any]:
        auth = embedded_auth_token_status()
        return {
            "running": self.running,
            "connected": self.connected,
            "client": self.client,
            "error": self.error,
            "host": host or embedded_host(),
            "port": port or embedded_port(),
            "bridge_version": EMBEDDED_BRIDGE_VERSION,
            "protocol_version": EMBEDDED_PROTOCOL_VERSION,
            "auth_required": True,
            "auth_path": auth["auth_path"],
            "auth_token_present": auth["auth_token_present"],
            "auth_token_valid": auth["auth_token_valid"],
        }


def _extract_auth_token(payload: dict[str, Any]) -> str | None:
    token = payload.get("auth_token")
    if isinstance(token, str) and token:
        return token
    params = payload.get("params")
    if isinstance(params, dict):
        token = params.get("auth_token")
        if isinstance(token, str) and token:
            return token
    return None


def _authorizer_url(*args, **kwargs):
    return None


def _request_authorized_command_context(*args, **kwargs):
    return None


def _command_auth_context(*args, **kwargs):
    return __import__("cutagent_cli.local_admission", fromlist=["embedded_command_context"]).embedded_command_context(args[0] if args else kwargs.get("params", {}))


class EmbeddedBridgeClient:
    """One-shot client used by CutAgent CLI invocations."""

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        timeout: float | None = None,
        auth_token: str | None = None,
    ):
        auth_config = read_embedded_auth_config() if host is None or port is None else {}
        self.host = host or _valid_loopback_host(auth_config.get("host")) or embedded_host()
        self.port = port or _valid_port(auth_config.get("port")) or embedded_port()
        self.timeout = embedded_request_timeout_seconds() if timeout is None else timeout
        self.auth_token = auth_token

    def _timeout_details(self, *, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return _embedded_timeout_details(
            method=method,
            params=params,
            timeout_s=self.timeout,
            host=self.host,
            port=self.port,
        )

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        token = self.auth_token or read_embedded_auth_token()
        payload = {
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or {},
            "protocol_version": EMBEDDED_PROTOCOL_VERSION,
        }
        if token:
            payload["auth_token"] = token
        if method == "execute" and _execute_params_require_command_auth(params):
            command_auth = _command_auth_context(params)
            if command_auth:
                payload["command_auth"] = command_auth
        try:
            with create_embedded_client_connection(self.host, self.port, self.timeout) as sock:
                sock.settimeout(self.timeout)
                sock.sendall(_dumps(payload))
                chunks = bytearray()
                while True:
                    char = sock.recv(1)
                    if not char:
                        break
                    if char == b"\n":
                        break
                    chunks.extend(char)
        except socket.timeout as exc:
            raise EmbeddedBridgeTimeout(
                "Timed out waiting for embedded bridge response.",
                details=self._timeout_details(method=method, params=params),
            ) from exc
        except (ConnectionRefusedError, OSError) as exc:
            raise EmbeddedBridgeNotRunning(details={"host": self.host, "port": self.port, "error": str(exc)}) from exc
        if not chunks:
            raise EmbeddedBridgeNotRunning(details={"host": self.host, "port": self.port, "error": "empty_response"})
        response = _loads(bytes(chunks))
        if response.get("error"):
            error = response["error"] if isinstance(response["error"], dict) else {}
            code = str(error.get("code") or "API_CALL_FAILED")
            message = str(error.get("message") or "Embedded bridge request failed.")
            details = error.get("details") if isinstance(error.get("details"), dict) else {}
            if code == "EMBEDDED_BRIDGE_NOT_RUNNING":
                raise EmbeddedBridgeNotRunning(message, details=details)
            if code == "EMBEDDED_BRIDGE_OUTDATED":
                raise EmbeddedBridgeOutdated(message, details=details)
            if code == "EMBEDDED_BRIDGE_TIMEOUT":
                raise EmbeddedBridgeTimeout(message, details=details)
            if code == "EMBEDDED_BRIDGE_AUTH_FAILED":
                raise EmbeddedBridgeAuthFailed(message, details=details)
            raise APICallFailed(message, details={"embedded_error_code": code, **details})
        return response.get("result")

    def status(self) -> dict[str, Any]:
        try:
            result = self.request("status")
        except EmbeddedBridgeNotRunning as exc:
            return EmbeddedServerStatus(running=False, error=str(exc)).as_dict(host=self.host, port=self.port)
        except (EmbeddedBridgeOutdated, EmbeddedBridgeTimeout, EmbeddedBridgeAuthFailed, APICallFailed) as exc:
            status = EmbeddedServerStatus(running=True, error=str(exc)).as_dict(host=self.host, port=self.port)
            status["error_code"] = getattr(exc, "code", exc.__class__.__name__)
            details = getattr(exc, "details", None)
            if isinstance(details, dict):
                status["error_details"] = details
            return status
        if not isinstance(result, dict):
            return EmbeddedServerStatus(running=True, error="invalid_status_response").as_dict(host=self.host, port=self.port)
        return result

    def ping(self) -> dict[str, Any]:
        result = self.request("ping")
        return result if isinstance(result, dict) else {"pong": bool(result)}

    def execute(self, params: dict[str, Any]) -> Any:
        return self.request("execute", params)


class EmbeddedBridgeServer:
    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        request_timeout: float | None = None,
        auth_token: str | None = None,
        auth_path: Path | None = None,
        publish_auth: bool = True,
    ):
        self.host = host or embedded_host()
        self.port = port or embedded_port()
        self.request_timeout = embedded_request_timeout_seconds() if request_timeout is None else request_timeout
        self.auth_token = auth_token or os.environ.get("DAVINCI_RESOLVE_SDK_EMBEDDED_AUTH_TOKEN", "").strip() or secrets.token_urlsafe(32)
        self.auth_path = auth_path or embedded_auth_path()
        self.publish_auth = publish_auth
        self.lua_reader: asyncio.StreamReader | None = None
        self.lua_writer: asyncio.StreamWriter | None = None
        self.lua_info: dict[str, Any] | None = None
        self.lua_lock = asyncio.Lock()
        self.http_info: dict[str, Any] | None = None
        self.http_client_id: str | None = None
        self.http_last_seen: float | None = None
        self.http_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.http_responses: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.spool_paths = embedded_spool_paths(auth_path=self.auth_path)
        self.spool_info: dict[str, Any] | None = None
        self.spool_last_seen: float | None = None

    async def start(self) -> None:
        server = await asyncio.start_server(self._handle_client, self.host, self.port)
        if self.publish_auth:
            write_embedded_auth_token(self.auth_token, host=self.host, port=self.port, auth_path=self.auth_path)
            atexit.register(remove_embedded_auth_token, self.auth_token, auth_path=self.auth_path)
        async with server:
            await server.serve_forever()

    def _status(self) -> dict[str, Any]:
        socket_connected = self.lua_writer is not None and not self.lua_writer.is_closing()
        http_connected = self._http_connected()
        spool_connected = self._spool_connected()
        connected = socket_connected or http_connected or spool_connected
        client = (
            self.lua_info
            if socket_connected
            else self.http_info
            if http_connected
            else self.spool_info
            if spool_connected
            else None
        )
        return EmbeddedServerStatus(
            running=True,
            connected=connected,
            client=client,
        ).as_dict(host=self.host, port=self.port)

    def _http_connected(self) -> bool:
        if any(not future.done() for future in self.http_responses.values()):
            return True
        return bool(self.http_last_seen and (time.time() - self.http_last_seen) < HTTP_CONNECTED_TTL_SECONDS)

    def _spool_connected(self) -> bool:
        return bool(
            self.spool_info
            and self.spool_last_seen
            and (time.time() - self.spool_last_seen) < SPOOL_CONNECTED_TTL_SECONDS
        )

    def _record_spool_response(self, payload: dict[str, Any], *, fresh: bool = False) -> bool:
        if not self._auth_ok(payload):
            return False
        client = payload.get("client")
        if isinstance(client, dict):
            self.spool_info = {
                **client,
                "connection": "file_spool",
                "server_bridge_version": EMBEDDED_BRIDGE_VERSION,
                "cli_version": __version__,
            }
        if self.spool_info is not None:
            if fresh:
                self.spool_last_seen = time.time()
            else:
                updated_at = payload.get("updated_at")
                if (
                    isinstance(updated_at, (int, float))
                    and not isinstance(updated_at, bool)
                    and 0 <= time.time() - float(updated_at) < SPOOL_CONNECTED_TTL_SECONDS
                ):
                    self.spool_last_seen = float(updated_at)
        return True

    async def _spool_round_trip(
        self,
        request: dict[str, Any],
        *,
        accept_timeout: float,
        response_timeout: float,
    ) -> dict[str, Any]:
        request_id = str(request.get("id") or uuid.uuid4())
        forwarded = {
            **request,
            "id": request_id,
            "auth_token": self.auth_token,
            "created_at": time.time(),
            "expires_at": time.time() + max(response_timeout, accept_timeout) + 5.0,
        }
        write_embedded_spool_payload(self.spool_paths["request"], forwarded)
        accepted = False
        accepted_deadline = time.monotonic() + accept_timeout
        response_deadline = time.monotonic() + response_timeout
        try:
            while True:
                payload = read_embedded_spool_response(self.spool_paths["response"])
                if (
                    isinstance(payload, dict)
                    and str(payload.get("id") or "") == request_id
                    and self._record_spool_response(payload, fresh=True)
                ):
                    state = str(payload.get("state") or "complete")
                    if state == "accepted":
                        accepted = True
                        # The Lua script has already loaded the request into
                        # memory. Remove the command file immediately so a
                        # script restart cannot replay an accepted mutation.
                        try:
                            self.spool_paths["request"].unlink()
                        except OSError:
                            pass
                    elif state == "complete":
                        return {
                            "id": request_id,
                            "result": payload.get("result"),
                            "error": payload.get("error"),
                        }
                now = time.monotonic()
                if not accepted and now >= accepted_deadline:
                    raise EmbeddedBridgeNotRunning(
                        "CutAgent.lua did not accept the file-spool request.",
                        details={
                            "connection": "file_spool",
                            "request_path": str(self.spool_paths["request"]),
                        },
                    )
                if now >= response_deadline:
                    raise EmbeddedBridgeTimeout(
                        "Timed out waiting for CutAgent.lua file-spool response.",
                        details={
                            "connection": "file_spool",
                            "request_id": request_id,
                            "timeout_s": response_timeout,
                        },
                    )
                await asyncio.sleep(SPOOL_POLL_INTERVAL_SECONDS)
        finally:
            try:
                self.spool_paths["request"].unlink()
            except OSError:
                pass

    async def _refresh_spool_status(self) -> None:
        socket_connected = self.lua_writer is not None and not self.lua_writer.is_closing()
        if socket_connected or self._http_connected():
            return
        latest = read_embedded_spool_response(self.spool_paths["response"])
        if isinstance(latest, dict):
            self._record_spool_response(latest)
        if self._spool_connected() or self.lua_lock.locked():
            return
        async with self.lua_lock:
            try:
                response = await self._spool_round_trip(
                    {
                        "id": f"spool-probe-{uuid.uuid4()}",
                        "method": "probe",
                        "params": {},
                    },
                    accept_timeout=1.5,
                    response_timeout=2.0,
                )
            except (EmbeddedBridgeNotRunning, EmbeddedBridgeTimeout):
                return
            if isinstance(response.get("result"), dict):
                client = response["result"].get("client")
                if isinstance(client, dict):
                    self.spool_info = {
                        **client,
                        "connection": "file_spool",
                        "server_bridge_version": EMBEDDED_BRIDGE_VERSION,
                        "cli_version": __version__,
                    }
                    self.spool_last_seen = time.time()

    async def _send(self, writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
        writer.write(_dumps(payload))
        await writer.drain()

    def _auth_ok(self, payload: dict[str, Any]) -> bool:
        return secrets.compare_digest(_extract_auth_token(payload) or "", self.auth_token)

    def _auth_error(self, req_id: Any = None) -> dict[str, Any]:
        return {
            "id": req_id,
            "result": None,
            "error": {
                "code": "EMBEDDED_BRIDGE_AUTH_FAILED",
                "message": "Embedded bridge authentication failed.",
            },
        }

    async def _read_json_line(self, reader: asyncio.StreamReader, *, timeout: float | None = None) -> dict[str, Any]:
        line = await asyncio.wait_for(reader.readline(), timeout=timeout or self.request_timeout)
        if not line:
            raise ConnectionError("client disconnected")
        return _loads(line)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            first_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not first_line:
                raise ConnectionError("client disconnected")
            if first_line.startswith((b"GET ", b"POST ")):
                await self._handle_http_request(first_line, reader, writer)
                return
            first = _loads(first_line)
            params = first.get("params") if isinstance(first.get("params"), dict) else {}
            if first.get("method") == "focus" and params.get("role") == "lua":
                if not self._auth_ok(first):
                    await self._send(writer, self._auth_error(first.get("id")))
                    return
                focused = request_cutagent_focus_from_embedded_script()
                await self._send(
                    writer,
                    {
                        "id": first.get("id"),
                        "result": {"ok": True, "focused": focused},
                        "error": None,
                    },
                )
                return
            if first.get("method") == "hello" and params.get("role") == "lua":
                if not self._auth_ok(first):
                    await self._send(writer, self._auth_error(first.get("id")))
                    return
                await self._register_lua_client(first, params, reader, writer)
                return
            response = await self._handle_command_request(first)
            await self._send(writer, response)
        except Exception as exc:
            try:
                await self._send(
                    writer,
                    {
                        "id": None,
                        "result": None,
                        "error": {
                            "code": "API_CALL_FAILED",
                            "message": str(exc),
                            "details": {"type": exc.__class__.__name__},
                        },
                    },
                )
            except Exception:
                pass
        finally:
            if writer is not self.lua_writer:
                writer.close()
                await writer.wait_closed()

    async def _register_lua_client(
        self,
        first: dict[str, Any],
        params: dict[str, Any],
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        protocol = int(params.get("protocol_version") or 0)
        if protocol != EMBEDDED_PROTOCOL_VERSION:
            await self._send(
                writer,
                {
                    "id": first.get("id"),
                    "result": None,
                    "error": {
                        "code": "EMBEDDED_BRIDGE_OUTDATED",
                        "message": "CutAgent.lua protocol version does not match CutAgent CLI.",
                        "details": {
                            "expected_protocol_version": EMBEDDED_PROTOCOL_VERSION,
                            "actual_protocol_version": protocol,
                        },
                    },
                },
            )
            writer.close()
            await writer.wait_closed()
            return
        if self.lua_writer and not self.lua_writer.is_closing():
            self.lua_writer.close()
        self.lua_reader = reader
        self.lua_writer = writer
        self.lua_info = {
            **params,
            "connected_at": time.time(),
            "server_bridge_version": EMBEDDED_BRIDGE_VERSION,
            "cli_version": __version__,
        }
        request_cutagent_focus_from_embedded_script()
        await self._send(writer, {"id": first.get("id"), "result": {"ok": True, "status": "registered"}, "error": None})
        try:
            while not reader.at_eof():
                await asyncio.sleep(0.5)
        finally:
            if writer is self.lua_writer:
                self.lua_reader = None
                self.lua_writer = None
                self.lua_info = None
            writer.close()
            await writer.wait_closed()

    async def _handle_http_request(
        self,
        first_line: bytes,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            parts = first_line.decode("ascii", errors="replace").strip().split()
            method = parts[0] if parts else ""
            path = parts[1] if len(parts) > 1 else "/"
            headers: dict[str, str] = {}
            while True:
                line = await reader.readline()
                if not line or line in (b"\r\n", b"\n"):
                    break
                text = line.decode("utf-8", errors="replace")
                name, _, value = text.partition(":")
                headers[name.strip().lower()] = value.strip()
            length = int(headers.get("content-length") or 0)
            body = await reader.readexactly(length) if length else b""
            payload = json.loads(body.decode("utf-8")) if body else {}
            if not isinstance(payload, dict):
                raise ValueError("HTTP bridge payload must be a JSON object")
            if method != "POST":
                await self._send_http(writer, 405, {"error": {"code": "VALIDATION_ERROR", "message": "POST required"}})
                return
            if not self._auth_ok(payload):
                await self._send_http(writer, 401, {"error": self._auth_error().get("error")})
                return
            if path == "/lua/hello":
                result = self._register_http_lua_client(payload)
                await self._send_http(writer, 200, {"result": result, "error": None})
                return
            if path == "/lua/poll":
                client_id = str(payload.get("client_id") or "").strip()
                if self.http_client_id and client_id != self.http_client_id:
                    await self._send_http(
                        writer,
                        409,
                        {
                            "request": None,
                            "error": {
                                "code": "EMBEDDED_BRIDGE_CLIENT_REPLACED",
                                "message": "A newer CutAgent.lua HTTP polling client is active.",
                                "details": {
                                    "active_client_id": self.http_client_id,
                                    "client_id": client_id or None,
                                },
                            },
                        },
                    )
                    return
                self.http_last_seen = time.time()
                request = None
                try:
                    request = await asyncio.wait_for(self.http_queue.get(), timeout=HTTP_POLL_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    pass
                await self._send_http(writer, 200, {"request": request, "error": None})
                return
            if path == "/lua/respond":
                response_id = str(payload.get("id") or "")
                future = self.http_responses.pop(response_id, None)
                if future and not future.done():
                    future.set_result(
                        {
                            "id": response_id,
                            "result": payload.get("result"),
                            "error": payload.get("error"),
                        }
                    )
                self.http_last_seen = time.time()
                await self._send_http(writer, 200, {"result": {"ok": True}, "error": None})
                return
            await self._send_http(writer, 404, {"error": {"code": "VALIDATION_ERROR", "message": "Unknown endpoint"}})
        except Exception as exc:
            await self._send_http(
                writer,
                500,
                {"error": {"code": "API_CALL_FAILED", "message": str(exc), "details": {"type": exc.__class__.__name__}}},
            )

    async def _send_http(self, writer: asyncio.StreamWriter, status: int, payload: dict[str, Any]) -> None:
        reason = {
            200: "OK",
            401: "Unauthorized",
            404: "Not Found",
            405: "Method Not Allowed",
            500: "Internal Server Error",
        }.get(status, "OK")
        body = json.dumps(
            payload,
            separators=(",", ":"),
            ensure_ascii=False,
            default=_json_default,
        ).encode("utf-8")
        writer.write(
            (
                f"HTTP/1.1 {status} {reason}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode("ascii")
            + body
        )
        await writer.drain()

    def _register_http_lua_client(self, payload: dict[str, Any]) -> dict[str, Any]:
        params = payload.get("params") if isinstance(payload.get("params"), dict) else payload
        protocol = int(params.get("protocol_version") or 0)
        if protocol != EMBEDDED_PROTOCOL_VERSION:
            return {
                "ok": False,
                "status": "outdated",
                "expected_protocol_version": EMBEDDED_PROTOCOL_VERSION,
                "actual_protocol_version": protocol,
            }
        connected_at = time.time()
        client_id = str(params.get("client_id") or uuid.uuid4()).strip()
        if not client_id:
            client_id = str(uuid.uuid4())
        self.http_client_id = client_id
        self.http_info = {
            **params,
            "client_id": client_id,
            "role": "lua",
            "connection": "http_poll",
            "connected_at": connected_at,
            "server_bridge_version": EMBEDDED_BRIDGE_VERSION,
            "cli_version": __version__,
        }
        request_cutagent_focus_from_embedded_script()
        return {"ok": True, "status": "registered", "connection": "http_poll"}

    def _verify_command_auth(self, request, params):
        from .local_admission import verify_embedded_command_context
        if not hasattr(self, "_local_command_contexts"):
            self._local_command_contexts = {}
        return verify_embedded_command_context(request.get("command_auth"), params, self._local_command_contexts)

    def _execute_policy_error(self, req_id: Any, code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "id": req_id,
            "result": None,
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
        }

    def _validate_execute_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        req_id = request.get("id")
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        op = params.get("op")
        if op == "get_version":
            return None
        if op != "call":
            return self._execute_policy_error(
                req_id,
                "VALIDATION_ERROR",
                f"Unknown embedded execute op: {op}",
                {"op": op},
            )
        method = params.get("method")
        if not isinstance(method, str) or method not in SUPPORTED_RESOLVE_METHODS:
            return self._execute_policy_error(
                req_id,
                "VALIDATION_ERROR",
                f"Unsupported embedded DaVinci Resolve method: {method}",
                {"method": method, "supported": sorted(SUPPORTED_RESOLVE_METHODS)},
            )
        if method in MUTATING_RESOLVE_METHODS:
            try:
                self._verify_command_auth(request, params)
            except Exception as exc:
                return self._execute_policy_error(
                    req_id,
                    "EMBEDDED_BRIDGE_POLICY_DENIED",
                    "Mutating embedded DaVinci Resolve method requires CLI policy authorization.",
                    {
                        "method": method,
                        "destructive": method in DESTRUCTIVE_RESOLVE_METHODS,
                        "reason": str(exc),
                    },
                )
        return None

    async def _handle_command_request(self, request: dict[str, Any]) -> dict[str, Any]:
        req_id = request.get("id")
        method = request.get("method")
        if not self._auth_ok(request):
            return self._auth_error(req_id)
        if method == "status":
            await self._refresh_spool_status()
            return {"id": req_id, "result": self._status(), "error": None}
        if method == "ping":
            await self._refresh_spool_status()
            return {"id": req_id, "result": {"pong": True, **self._status()}, "error": None}
        if method != "execute":
            return {
                "id": req_id,
                "result": None,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": f"Unknown embedded bridge method: {method}",
                    "details": {"method": method},
                },
            }
        policy_error = self._validate_execute_request(request)
        if policy_error:
            return policy_error
        socket_connected = self.lua_reader and self.lua_writer and not self.lua_writer.is_closing()
        if not socket_connected and self._http_connected():
            async with self.lua_lock:
                return await self._execute_via_http_lua(request)
        if not socket_connected and self.http_info is not None and not self._spool_connected():
            latest = read_embedded_spool_response(self.spool_paths["response"])
            if isinstance(latest, dict):
                self._record_spool_response(latest)
            if not self._spool_connected():
                return {
                    "id": req_id,
                    "result": None,
                    "error": {
                        "code": "EMBEDDED_BRIDGE_NOT_RUNNING",
                        "message": "CutAgent.lua is not connected.",
                        "details": self._status(),
                    },
                }
        if not socket_connected:
            async with self.lua_lock:
                try:
                    return await self._execute_via_spool_lua(request)
                except EmbeddedBridgeNotRunning as exc:
                    return {
                        "id": req_id,
                        "result": None,
                        "error": {
                            "code": exc.code,
                            "message": str(exc),
                            "details": {**self._status(), **getattr(exc, "details", {})},
                        },
                    }
                except EmbeddedBridgeTimeout as exc:
                    return {
                        "id": req_id,
                        "result": None,
                        "error": {
                            "code": exc.code,
                            "message": str(exc),
                            "details": {
                                **_embedded_timeout_details(
                                    method=str(request.get("method") or ""),
                                    params=request.get("params") if isinstance(request.get("params"), dict) else None,
                                    timeout_s=self.request_timeout,
                                ),
                                **getattr(exc, "details", {}),
                            },
                        },
                    }
        async with self.lua_lock:
            try:
                await self._send(
                    self.lua_writer,
                    {
                        "id": str(req_id),
                        "method": "execute",
                        "auth_token": self.auth_token,
                        "params": request.get("params") if isinstance(request.get("params"), dict) else {},
                    },
                )
                response = await self._read_json_line(self.lua_reader, timeout=self.request_timeout)
                if not self._auth_ok(response):
                    return self._auth_error(req_id)
            except asyncio.TimeoutError:
                return {
                    "id": req_id,
                    "result": None,
                    "error": {
                        "code": "EMBEDDED_BRIDGE_TIMEOUT",
                        "message": "Timed out waiting for CutAgent.lua.",
                        "details": _embedded_timeout_details(
                            method=str(request.get("method") or ""),
                            params=request.get("params") if isinstance(request.get("params"), dict) else None,
                            timeout_s=self.request_timeout,
                        ),
                    },
                }
            except Exception as exc:
                return {
                    "id": req_id,
                    "result": None,
                    "error": {
                        "code": "EMBEDDED_BRIDGE_NOT_RUNNING",
                        "message": "CutAgent.lua disconnected.",
                        "details": {"error": str(exc)},
                    },
                }
        response["id"] = req_id
        return response

    async def _execute_via_spool_lua(self, request: dict[str, Any]) -> dict[str, Any]:
        response = await self._spool_round_trip(
            {
                "id": str(request.get("id")),
                "method": "execute",
                "params": request.get("params") if isinstance(request.get("params"), dict) else {},
            },
            accept_timeout=SPOOL_ACCEPT_TIMEOUT_SECONDS,
            response_timeout=self.request_timeout,
        )
        response["id"] = request.get("id")
        return response

    async def _execute_via_http_lua(self, request: dict[str, Any]) -> dict[str, Any]:
        req_id = str(request.get("id"))
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self.http_responses[req_id] = future
        await self.http_queue.put(
            {
                "id": req_id,
                "method": "execute",
                "auth_token": self.auth_token,
                "client_id": self.http_client_id,
                "params": request.get("params") if isinstance(request.get("params"), dict) else {},
            }
        )
        try:
            response = await asyncio.wait_for(future, timeout=self.request_timeout)
        except asyncio.TimeoutError:
            self.http_responses.pop(req_id, None)
            return {
                "id": request.get("id"),
                "result": None,
                "error": {
                    "code": "EMBEDDED_BRIDGE_TIMEOUT",
                    "message": "Timed out waiting for CutAgent.lua.",
                    "details": _embedded_timeout_details(
                        method=str(request.get("method") or ""),
                        params=request.get("params") if isinstance(request.get("params"), dict) else None,
                        timeout_s=self.request_timeout,
                    ),
                },
            }
        response["id"] = request.get("id")
        return response


def run_embedded_server(*, host: str | None = None, port: int | None = None, request_timeout: float | None = None) -> None:
    try:
        asyncio.run(EmbeddedBridgeServer(host=host, port=port, request_timeout=request_timeout).start())
    except OSError as exc:
        raise ValidationError(
            "Failed to start embedded bridge server.",
            details={"host": host or embedded_host(), "port": port or embedded_port(), "error": str(exc)},
        ) from exc
