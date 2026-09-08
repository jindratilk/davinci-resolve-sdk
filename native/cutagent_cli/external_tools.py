"""External tool discovery and version probing."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .config import get_config
from .errors import ExternalToolNotFound

_OVERRIDES: dict[str, str] = {}
_MEDIA_TOOLS = {"ffmpeg", "ffprobe"}
_STRICT_MEDIA_TOOLS_ENV = "CUTAGENT_REQUIRE_BUNDLED_MEDIA_TOOLS"


def set_tool_override(tool: str, path: Optional[str]) -> None:
    """Set per-process override for an external tool path."""
    if not path:
        _OVERRIDES.pop(tool, None)
        return
    _OVERRIDES[tool] = path


def get_tool_override(tool: str) -> Optional[str]:
    """Get per-process override for a tool, if set."""
    return _OVERRIDES.get(tool)


def env_override_name(tool: str) -> str:
    return f"CUTAGENT_{tool.upper()}_PATH"


def _is_executable_file(path: str) -> bool:
    p = Path(os.path.expanduser(path))
    return p.is_file() and os.access(p, os.X_OK)


def _truthy_env(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _requires_bundled_media_tool(tool: str) -> bool:
    return tool in _MEDIA_TOOLS and _truthy_env(os.environ.get(_STRICT_MEDIA_TOOLS_ENV))


def _resolve_required_bundled_media_tool(tool: str) -> str:
    env_var = env_override_name(tool)
    env_path = os.environ.get(env_var)
    if env_path:
        expanded_env_path = os.path.expanduser(env_path)
        if _is_executable_file(expanded_env_path):
            return expanded_env_path
        raise ExternalToolNotFound(
            f"{tool} bundled runtime path is not executable: {expanded_env_path}",
            details={
                "tool": tool,
                "env_var": env_var,
                "env_path": expanded_env_path,
                "strict_env": _STRICT_MEDIA_TOOLS_ENV,
            },
        )

    raise ExternalToolNotFound(
        f"{tool} is required from the bundled CutAgent runtime in production.",
        details={"tool": tool, "env_var": env_var, "strict_env": _STRICT_MEDIA_TOOLS_ENV},
    )


def resolve_tool(tool: str) -> str:
    """Resolve a tool path, with strict bundled media tools in production."""
    if _requires_bundled_media_tool(tool):
        return _resolve_required_bundled_media_tool(tool)

    override = get_tool_override(tool)
    if override:
        if _is_executable_file(override):
            return os.path.expanduser(override)
        raise ExternalToolNotFound(
            f"{tool} override path is not executable: {override}",
            details={"tool": tool, "override": override},
        )

    env_path = os.environ.get(env_override_name(tool))
    if env_path:
        expanded_env_path = os.path.expanduser(env_path)
        if _is_executable_file(expanded_env_path):
            return expanded_env_path
        raise ExternalToolNotFound(
            f"{tool} environment path is not executable: {expanded_env_path}",
            details={"tool": tool, "env_var": env_override_name(tool), "env_path": expanded_env_path},
        )

    cfg = get_config().get("tools", f"{tool}_path")
    if cfg:
        cfg_path = os.path.expanduser(str(cfg))
        if _is_executable_file(cfg_path):
            return cfg_path
        raise ExternalToolNotFound(
            f"{tool} configured path is not executable: {cfg_path}",
            details={"tool": tool, "config_path": cfg_path},
        )

    discovered = shutil.which(tool)
    if discovered:
        return discovered

    raise ExternalToolNotFound(
        f"{tool} not found in PATH. Install it or pass --{tool}-path.",
        details={"tool": tool},
    )


def probe_tool_version(tool: str) -> dict[str, str | bool]:
    """Return resolved path and first --version line."""
    path = resolve_tool(tool)
    proc = subprocess.run(
        [path, "-version"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    first_line = ""
    if proc.stdout:
        first_line = proc.stdout.splitlines()[0]
    elif proc.stderr:
        first_line = proc.stderr.splitlines()[0]
    return {
        "tool": tool,
        "path": path,
        "ok": proc.returncode == 0,
        "version": first_line.strip(),
    }
