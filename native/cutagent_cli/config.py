"""Configuration management for cutagent-cli."""

from __future__ import annotations

import os
from typing import Any, Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # Fallback for Python 3.10
    except ImportError:
        tomllib = None  # type: ignore


# Default configuration
DEFAULT_CONFIG = {
    "general": {
        "default_format": "table",  # "table" or "json"
        "auto_refresh": True,
    },
    "resolve": {
        "script_path": None,  # Override DaVinciResolveScript path
    },
    "templates": {
        "directory": "~/resolve-templates/",
        "bold_style": "ExtraBold",
    },
    "render": {
        "default_target": "~/Desktop/renders/",
        "default_format": "mp4",
        "default_codec": "H.264",
    },
    "tools": {
        "ffmpeg_path": None,
        "ffprobe_path": None,
        "resolve_path": None,
    },
    "security": {
        "policy_profile": "auto_edit",  # read_only | auto_edit
    },
    "fusion": {
        "placeholder_text": ["PLACEHOLDER_TEXT", "TEXT_PLACEHOLDER", "__TEXT__"],
        "placeholder_styling": ["PLACEHOLDER_STYLING", "STYLING_PLACEHOLDER", "__STYLING__"],
        "placeholder_image": ["PLACEHOLDER_IMAGE", "IMAGE_PLACEHOLDER", "__IMAGE__"],
    },
}


class Config:
    """Configuration manager for cutagent-cli."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._default_config_path()
        self._data = DEFAULT_CONFIG.copy()
        self._load()

    @staticmethod
    def _default_config_path() -> str:
        """Get default config file path."""
        return os.path.expanduser("~/.cutagent-cli.toml")

    def _load(self) -> None:
        """Load config from TOML file if it exists."""
        if not os.path.isfile(self.config_path):
            return

        if tomllib is None:
            # TOML library not available — skip loading
            return

        try:
            with open(self.config_path, "rb") as f:
                user_config = tomllib.load(f)
            self._merge(user_config)
        except Exception:
            # Silently ignore config errors (don't break CLI)
            pass

    def _merge(self, user_config: dict) -> None:
        """Deep merge user config into defaults."""
        for section, values in user_config.items():
            if section in self._data and isinstance(values, dict):
                self._data[section].update(values)
            else:
                self._data[section] = values

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get config value."""
        return self._data.get(section, {}).get(key, default)

    def get_section(self, section: str) -> dict:
        """Get entire config section."""
        return self._data.get(section, {})

    @property
    def resolve_script_path(self) -> Optional[str]:
        """Get custom DaVinci Resolve script path if configured."""
        path = self.get("resolve", "script_path")
        return os.path.expanduser(path) if path else None

    @property
    def template_directory(self) -> str:
        """Get template directory (expanded)."""
        return os.path.expanduser(self.get("templates", "directory", "~/resolve-templates/"))

    @property
    def bold_style(self) -> str:
        """Get default bold style for CharacterLevelStyling."""
        return self.get("templates", "bold_style", "ExtraBold")

    @property
    def render_defaults(self) -> dict:
        """Get render defaults."""
        return self.get_section("render")


# Global config instance
_config: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    """Get or create global config instance."""
    global _config
    if _config is None or config_path:
        _config = Config(config_path)
    return _config
