"""DaVinci Resolve API transport adapters."""

from __future__ import annotations

import csv
import io
import ntpath
import os
import re
import socket
import stat
import subprocess
import sys
import uuid
from enum import Enum
from typing import Any, Protocol


from .embedded_bridge import (
    EMBEDDED_BRIDGE_VERSION,
    EMBEDDED_PROTOCOL_VERSION,
    EmbeddedBridgeClient,
    EmbeddedBridgeNotRunning,
    embedded_auth_token_status,
    installed_script_status,
)
from .errors import ResolveNotRunning, ResolveScriptingUnavailable


class ResolveTransport(str, Enum):
    STUDIO_EXTERNAL = "studio_external"
    EMBEDDED_FREE = "embedded_free"


class ResolveAdapter(Protocol):
    transport: ResolveTransport

    def connect(self) -> Any:
        ...

    def status(self) -> dict[str, Any]:
        ...


_RESOLVE_SCRIPT_PATHS = [
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
    os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"),
    "C:\\ProgramData\\Blackmagic Design\\DaVinci Resolve\\Support\\Developer\\Scripting\\Modules",
    "/opt/resolve/Developer/Scripting/Modules",
    "/opt/resolve/libs/Fusion/Modules",
]

_FUSION_LIB_PATHS = [
    "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion",
]

_last_resolve_script_import_error: str | None = None
EMBEDDED_STATUS_TIMEOUT_ENV = "DAVINCI_RESOLVE_SDK_EMBEDDED_STATUS_TIMEOUT_S"
DEFAULT_EMBEDDED_STATUS_TIMEOUT_SECONDS = 5.0
CUTAGENT_RESOLVE_UUID_ENV = "CUTAGENT_RESOLVE_UUID"
CUTAGENT_RESOLVE_HOST_ENV = "CUTAGENT_RESOLVE_HOST"
CUTAGENT_RESOLVE_PID_ENV = "CUTAGENT_RESOLVE_PID"
_TARGETED_RESOLVE_TIMEOUT_SECONDS = 2
_WORKER_IDENTITY_FILE = "cutagent-worker-identity.txt"
_RESOLVE_PROXY_UUID = re.compile(
    r"(?:^|[,\s])UUID:\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?=\])"
)


def resolve_instance_target_configured() -> bool:
    return any(os.environ.get(name) is not None for name in (CUTAGENT_RESOLVE_UUID_ENV, CUTAGENT_RESOLVE_HOST_ENV))


def _target_configuration_error(reason: str) -> ResolveScriptingUnavailable:
    return ResolveScriptingUnavailable(
        "The configured DaVinci Resolve worker target is unavailable.",
        details={"targeted_instance": True, "reason": reason},
    )


def _read_worker_identity(home: str) -> dict[str, str]:
    identity_path = os.path.join(home, _WORKER_IDENTITY_FILE)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(identity_path, flags)
    except OSError:
        raise _target_configuration_error("worker_identity_unavailable") from None
    try:
        identity_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(identity_stat.st_mode)
            or identity_stat.st_nlink != 1
            or identity_stat.st_uid != os.getuid()
            or identity_stat.st_size <= 0
            or identity_stat.st_size > 4096
        ):
            raise _target_configuration_error("worker_identity_invalid")
        payload = os.read(descriptor, 4097)
    except OSError:
        raise _target_configuration_error("worker_identity_unavailable") from None
    finally:
        os.close(descriptor)
    if len(payload) > 4096:
        raise _target_configuration_error("worker_identity_invalid")
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise _target_configuration_error("worker_identity_invalid") from None
    identity: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if not separator or key in identity or key not in {"uuid", "pid", "app"} or not value:
            raise _target_configuration_error("worker_identity_invalid")
        identity[key] = value
    if set(identity) != {"uuid", "pid", "app"} or not identity["pid"].isdigit() or identity["app"] != "Fusion":
        raise _target_configuration_error("worker_identity_invalid")
    return identity


def _account_home() -> str | None:
    try:
        import pwd

        return os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError, OSError):
        return None


def _targeted_worker_environment(instance_uuid: str) -> tuple[str, str, str, str]:
    home_raw = os.environ.get("HOME", "").strip()
    fixed_home_raw = os.environ.get("CFFIXED_USER_HOME", "").strip()
    temporary_raw = os.environ.get("TMPDIR", "").strip()
    if not home_raw or not os.path.isabs(home_raw):
        raise _target_configuration_error("isolated_worker_environment_required")

    home = os.path.realpath(home_raw)
    account_home = _account_home()

    if account_home == home:
        if fixed_home_raw and (
            not os.path.isabs(fixed_home_raw) or os.path.realpath(fixed_home_raw) != home
        ):
            raise _target_configuration_error("gui_home_environment_invalid")
        if temporary_raw and not os.path.isabs(temporary_raw):
            raise _target_configuration_error("gui_home_environment_invalid")
        return home, os.path.realpath(fixed_home_raw) if fixed_home_raw else home, (
            os.path.realpath(temporary_raw) if temporary_raw else ""
        ), instance_uuid

    if not account_home:
        raise _target_configuration_error("isolated_worker_environment_required")
    if not fixed_home_raw or not temporary_raw or any(
        not os.path.isabs(value) for value in (fixed_home_raw, temporary_raw)
    ):
        raise _target_configuration_error("isolated_worker_environment_required")
    fixed_home = os.path.realpath(fixed_home_raw)
    temporary = os.path.realpath(temporary_raw)
    if home != fixed_home or os.path.dirname(home) != os.path.dirname(temporary) or home == temporary:
        raise _target_configuration_error("isolated_worker_environment_invalid")
    identity = _read_worker_identity(home)
    effective_uuid = identity["uuid"].casefold()
    if effective_uuid != instance_uuid:
        try:
            from .core.owned_resolve_lifecycle import resolve_rotated_instance_uuid

            effective_uuid = resolve_rotated_instance_uuid(home, instance_uuid, identity)
        except Exception:
            raise _target_configuration_error("worker_identity_mismatch") from None
    return home, fixed_home, temporary, effective_uuid


def _resolve_instance_target() -> tuple[str, str] | None:
    if not resolve_instance_target_configured():
        return None
    if sys.platform != "darwin":
        raise _target_configuration_error("targeted_instance_platform_unsupported")

    raw_uuid = os.environ.get(CUTAGENT_RESOLVE_UUID_ENV, "").strip()
    if not raw_uuid:
        raise _target_configuration_error("instance_uuid_required")
    try:
        instance_uuid = str(uuid.UUID(raw_uuid))
    except (AttributeError, ValueError):
        raise _target_configuration_error("instance_uuid_invalid") from None
    if raw_uuid.casefold() != instance_uuid:
        raise _target_configuration_error("instance_uuid_invalid")

    _home, _fixed_home, _temporary, instance_uuid = _targeted_worker_environment(instance_uuid)
    raw_host = os.environ.get(CUTAGENT_RESOLVE_HOST_ENV, "").strip()
    try:
        host = socket.gethostbyname(raw_host or socket.gethostname())
    except (OSError, UnicodeError):
        raise _target_configuration_error("instance_host_unavailable") from None
    if not host:
        raise _target_configuration_error("instance_host_unavailable")
    return host, instance_uuid


def _resolve_instance_pid() -> int | None:
    """Return the caller-supplied exact process target when one is supplied."""

    raw = os.environ.get(CUTAGENT_RESOLVE_PID_ENV, "").strip()
    if not raw:
        return None
    try:
        pid = int(raw)
    except ValueError:
        raise _target_configuration_error("instance_pid_invalid") from None
    if pid <= 1 or str(pid) != raw:
        raise _target_configuration_error("instance_pid_invalid")
    return pid


def _assert_targeted_proxy_identity(resolve: Any, instance_uuid: str) -> None:
    try:
        description = str(resolve)
    except Exception:
        raise _target_configuration_error("instance_identity_unavailable") from None
    match = _RESOLVE_PROXY_UUID.search(description)
    if match is None:
        raise _target_configuration_error("instance_identity_unavailable")
    if match.group(1).casefold() != instance_uuid:
        raise _target_configuration_error("instance_identity_mismatch")


def _windows_system_directory() -> str | None:
    """Return the kernel-reported system directory without trusting PATH or cwd."""
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
        if length <= 0 or length >= len(buffer):
            return None
        return buffer.value
    except (AttributeError, OSError, ValueError):
        return None


def trusted_windows_system_executable(filename: str) -> str | None:
    """Resolve a Windows system executable without consulting PATH or cwd."""
    system_directory = _windows_system_directory()
    if not system_directory:
        return None
    return ntpath.join(system_directory, filename)


def _trusted_process_probe_command() -> list[str] | None:
    if sys.platform == "win32":
        tasklist = trusted_windows_system_executable("tasklist.exe")
        if not tasklist:
            return None
        return [
            tasklist,
            "/FI",
            "IMAGENAME eq Resolve.exe",
            "/FO",
            "CSV",
            "/NH",
        ]
    for candidate in ("/usr/bin/pgrep", "/bin/pgrep"):
        if os.path.isfile(candidate):
            return [candidate, "-x", "Resolve" if sys.platform == "darwin" else "resolve"]
    return None


def probe_resolve_process_running() -> bool | None:
    """Return process presence, or ``None`` when the trusted probe cannot decide."""
    command = _trusted_process_probe_command()
    if not command:
        return None
    try:
        if sys.platform == "win32":
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=2.0,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode != 0:
                return None
            rows = list(csv.reader(io.StringIO(completed.stdout)))
            return any(row and row[0].strip().casefold() == "resolve.exe" for row in rows)
        completed = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
            check=False,
        )
        if completed.returncode == 0:
            return True
        if completed.returncode == 1:
            return False
        return None
    except (OSError, subprocess.SubprocessError):
        return None


def is_resolve_process_running() -> bool:
    """Best-effort process probe used only to classify a missing API handle."""
    return probe_resolve_process_running() is True


def embedded_status_timeout_seconds(default: float = DEFAULT_EMBEDDED_STATUS_TIMEOUT_SECONDS) -> float:
    raw = os.environ.get(EMBEDDED_STATUS_TIMEOUT_ENV, "").strip()
    if not raw:
        return float(default)
    try:
        timeout = float(raw)
    except (TypeError, ValueError):
        return float(default)
    if timeout <= 0:
        return float(default)
    return timeout


def _format_resolve_script_import_error(exc: ImportError) -> str | None:
    message = str(exc).strip()
    if not message:
        return "DaVinciResolveScript import failed."

    lowered = message.lower()
    if "different team ids" in lowered or "not valid for use in process" in lowered:
        return (
            "DaVinciResolveScript found Blackmagic fusionscript.so, but macOS library "
            "validation rejected it because the loading process is signed by a different "
            "Team ID. Sign the packaged cutagent-cli Python runtime with "
            "com.apple.security.cs.disable-library-validation. Original error: "
            f"{message}"
        )

    if "fusionscript" in lowered or "could not locate module dependencies" in lowered or "dlopen" in lowered:
        return (
            "DaVinciResolveScript found the scripting module but failed to load its native "
            f"fusionscript dependency. Original error: {message}"
        )

    return None


def get_resolve_script_import_error() -> str | None:
    return _last_resolve_script_import_error


def ensure_resolve_paths() -> None:
    """Add DaVinci Resolve scripting module paths to sys.path if not present."""
    try:
        from .config import get_config

        config = get_config()
        custom_path = config.resolve_script_path
        if custom_path and os.path.isdir(custom_path) and custom_path not in sys.path:
            sys.path.insert(0, custom_path)
    except Exception:
        pass

    env_path = os.environ.get("RESOLVE_SCRIPT_API")
    if env_path and env_path not in sys.path:
        sys.path.insert(0, env_path)

    for path in _RESOLVE_SCRIPT_PATHS:
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

    for path in _FUSION_LIB_PATHS:
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

    for path in _FUSION_LIB_PATHS:
        if os.path.isdir(path):
            env_val = os.environ.get("DYLD_LIBRARY_PATH", "")
            if path not in env_val:
                os.environ["DYLD_LIBRARY_PATH"] = f"{path}:{env_val}" if env_val else path


def import_resolve_script():
    global _last_resolve_script_import_error
    ensure_resolve_paths()
    try:
        import DaVinciResolveScript as dvr

        _last_resolve_script_import_error = None
        return dvr
    except ImportError as exc:
        _last_resolve_script_import_error = _format_resolve_script_import_error(exc)
        return None


def _version_payload(resolve: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, method in (
        ("resolve_version", "GetVersion"),
        ("resolve_version_string", "GetVersionString"),
        ("product_name", "GetProductName"),
        ("current_page", "GetCurrentPage"),
    ):
        func = getattr(resolve, method, None)
        if callable(func):
            try:
                value = func()
            except Exception:
                value = None
            if value:
                payload[key] = value
    return payload


class StudioExternalAdapter:
    transport = ResolveTransport.STUDIO_EXTERNAL

    def __init__(self) -> None:
        self._dvr_script = None
        self.resolve = None

    def connect(self) -> Any:
        self._dvr_script = import_resolve_script()
        if self._dvr_script is None:
            import_error = get_resolve_script_import_error()
            if import_error:
                raise ResolveNotRunning(import_error)
            raise ResolveNotRunning(
                "DaVinciResolveScript module not found. "
                "Install DaVinci Resolve 20+ Studio or use the embedded_free transport."
            )
        scriptapp = getattr(self._dvr_script, "scriptapp", None)
        if not callable(scriptapp):
            raise ResolveNotRunning("DaVinciResolveScript module does not expose scriptapp().")
        target = _resolve_instance_target()
        if target is None:
            self.resolve = scriptapp("Resolve")
        else:
            host, instance_uuid = target
            try:
                self.resolve = scriptapp("Resolve", host, _TARGETED_RESOLVE_TIMEOUT_SECONDS, instance_uuid)
            except Exception:
                raise _target_configuration_error("targeted_connection_failed") from None
        if self.resolve is None:
            if target is not None:
                raise _target_configuration_error("targeted_connection_failed")
            if is_resolve_process_running():
                raise ResolveScriptingUnavailable(
                    details={
                        "process_running": True,
                        "studio_recovery": (
                            "Enable Preferences > System > General > External scripting using Local, "
                            "then restart DaVinci Resolve."
                        ),
                        "free_recovery": "Run Workspace > Scripts > CutAgent.",
                    }
                )
            raise ResolveNotRunning()
        if target is not None:
            _assert_targeted_proxy_identity(self.resolve, target[1])
        return self.resolve

    def status(self) -> dict[str, Any]:
        try:
            resolve = self.connect()
        except (ResolveNotRunning, ResolveScriptingUnavailable) as exc:
            return {
                "available": False,
                "connected": False,
                "error": str(exc),
                "error_code": exc.code,
                "recoverability": exc.recoverability,
                "error_details": exc.details,
            }
        return {
            "available": True,
            "connected": True,
            **_version_payload(resolve),
        }


class EmbeddedProxy:
    def __init__(self, adapter: "EmbeddedFreeAdapter", ref: str):
        self._adapter = adapter
        self._ref = ref

    @property
    def cutagent_ref(self) -> str:
        return self._ref

    def __getattr__(self, method: str):
        if method.startswith("__"):
            raise AttributeError(method)

        def _call(*args):
            return self._adapter.call(self._ref, method, list(args))

        return _call

    def __repr__(self) -> str:
        return f"<EmbeddedProxy {self._ref}>"


_EMBEDDED_OBJECT_LIST_METHODS = {
    "AddItemListToMediaPool",
    "AppendToTimeline",
    "GetClipList",
    "GetItemListInTrack",
    "GetSubFolderList",
    "GetTimelineList",
    "ImportMedia",
}


class EmbeddedFreeAdapter:
    transport = ResolveTransport.EMBEDDED_FREE

    def __init__(self, *, client: EmbeddedBridgeClient | None = None):
        self.client = client or EmbeddedBridgeClient()
        self.resolve = EmbeddedProxy(self, "resolve")

    def _status_client(self) -> EmbeddedBridgeClient:
        if isinstance(self.client, EmbeddedBridgeClient):
            return EmbeddedBridgeClient(
                host=self.client.host,
                port=self.client.port,
                timeout=min(self.client.timeout, embedded_status_timeout_seconds()),
                auth_token=self.client.auth_token,
            )
        return self.client

    def connect(self) -> Any:
        status = self._status_client().status()
        if not status.get("running") or not status.get("connected"):
            raise EmbeddedBridgeNotRunning(details=status)
        return self.resolve

    def _serialize_arg(self, value: Any) -> Any:
        if isinstance(value, EmbeddedProxy):
            return {"__cutagent_ref__": value.cutagent_ref}
        if isinstance(value, dict):
            return {key: self._serialize_arg(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._serialize_arg(item) for item in value]
        return value

    def _deserialize_result(self, value: Any) -> Any:
        if isinstance(value, dict):
            ref = value.get("__cutagent_ref__")
            if isinstance(ref, str):
                return EmbeddedProxy(self, ref)
            return {key: self._deserialize_result(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._deserialize_result(item) for item in value]
        return value

    def call(self, target: str, method: str, args: list[Any]) -> Any:
        result = self.client.execute(
            {
                "op": "call",
                "target": target,
                "method": method,
                "args": [self._serialize_arg(arg) for arg in args],
            }
        )
        deserialized = self._deserialize_result(result)
        if method in _EMBEDDED_OBJECT_LIST_METHODS and isinstance(deserialized, dict):
            return list(deserialized.values())
        return deserialized

    def status(self) -> dict[str, Any]:
        status = self._status_client().status()
        script = installed_script_status()
        auth = embedded_auth_token_status()
        error_details = status.get("error_details") if isinstance(status.get("error_details"), dict) else None
        return {
            "installed": script["installed"],
            "current": script["current"],
            "running": status.get("running", False),
            "connected": status.get("connected", False),
            "client": status.get("client"),
            "host": status.get("host"),
            "port": status.get("port"),
            "bridge_version": EMBEDDED_BRIDGE_VERSION,
            "protocol_version": EMBEDDED_PROTOCOL_VERSION,
            "auth_path": auth["auth_path"],
            "auth_token_present": auth["auth_token_present"],
            "auth_token_valid": auth["auth_token_valid"],
            "server": status,
            "server_error": status.get("error"),
            "server_error_code": status.get("error_code"),
            "server_error_details": error_details,
            "script": script,
        }


def requested_transport() -> ResolveTransport | None:
    raw = os.environ.get("CUTAGENT_RESOLVE_TRANSPORT", "").strip().lower()
    if not raw or raw == "auto":
        return None
    for transport in ResolveTransport:
        if raw == transport.value:
            return transport
    return None


def create_adapter(transport: ResolveTransport) -> ResolveAdapter:
    if transport == ResolveTransport.STUDIO_EXTERNAL:
        return StudioExternalAdapter()
    if transport == ResolveTransport.EMBEDDED_FREE:
        return EmbeddedFreeAdapter()
    raise ValueError(f"Unknown DaVinci Resolve transport: {transport}")


def _embedded_status_owns_transport(status: dict[str, Any]) -> bool:
    return bool(status.get("connected") is True)


def _skipped_studio_external_status(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "connected": False,
        "skipped": True,
        "reason": reason,
        "error": "Studio external transport probe skipped because DaVinci Resolve Free embedded transport is configured.",
    }


def _skipped_embedded_free_status(reason: str) -> dict[str, Any]:
    return {
        "installed": False,
        "current": False,
        "running": False,
        "connected": False,
        "skipped": True,
        "reason": reason,
        "error": "DaVinci Resolve Free embedded transport probe skipped because DaVinci Resolve Studio transport is active.",
    }


def select_adapter() -> ResolveAdapter:
    requested = requested_transport()
    if resolve_instance_target_configured():
        if requested == ResolveTransport.EMBEDDED_FREE:
            raise _target_configuration_error("targeted_instance_requires_studio_external")
        adapter = StudioExternalAdapter()
        adapter.connect()
        return adapter
    if requested is not None:
        adapter = create_adapter(requested)
        adapter.connect()
        return adapter

    embedded = EmbeddedFreeAdapter()
    try:
        embedded_status = embedded.status()
    except Exception:
        embedded_status = {}
    if _embedded_status_owns_transport(embedded_status):
        embedded.connect()
        return embedded

    external = StudioExternalAdapter()
    try:
        external.connect()
        return external
    except ResolveScriptingUnavailable:
        raise
    except ResolveNotRunning:
        pass

    embedded.connect()
    return embedded


def transport_status() -> dict[str, Any]:
    requested = requested_transport()

    if resolve_instance_target_configured():
        external = StudioExternalAdapter().status()
        embedded = _skipped_embedded_free_status("targeted_studio_instance_configured")
    elif requested == ResolveTransport.STUDIO_EXTERNAL:
        external = StudioExternalAdapter().status()
        embedded = _skipped_embedded_free_status("studio_external_configured")
    elif requested == ResolveTransport.EMBEDDED_FREE:
        embedded = EmbeddedFreeAdapter().status()
        external = _skipped_studio_external_status("embedded_free_configured")
    else:
        embedded = EmbeddedFreeAdapter().status()
        if _embedded_status_owns_transport(embedded):
            external = _skipped_studio_external_status("embedded_free_configured")
        else:
            external = StudioExternalAdapter().status()

    active_transport = None
    if external.get("connected"):
        active_transport = ResolveTransport.STUDIO_EXTERNAL.value
    elif embedded.get("connected"):
        active_transport = ResolveTransport.EMBEDDED_FREE.value

    version = external.get("resolve_version_string") or external.get("resolve_version")
    product = external.get("product_name")
    client = embedded.get("client") if isinstance(embedded.get("client"), dict) else {}
    if not version and isinstance(client, dict):
        version = client.get("resolve_version")
    if not product and isinstance(client, dict):
        product = client.get("product")

    edition = None
    product_text = str(product or "").lower()
    if "studio" in product_text:
        edition = "studio"
    elif product:
        edition = "free"

    return {
        "active_transport": active_transport,
        "studio_external": external,
        "embedded_free": embedded,
        "resolve_version": version,
        "product_name": product,
        "edition": edition,
    }
