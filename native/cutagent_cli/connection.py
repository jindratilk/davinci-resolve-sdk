"""DaVinci Resolve connection singleton."""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from typing import Any, Callable, Optional

from .adapters import ResolveTransport, ensure_resolve_paths, import_resolve_script, select_adapter
from .errors import APICallFailed, ResolveNotRunning, NoProjectOpen, NoTimelineOpen

logger = logging.getLogger("cutagent-cli")

def _ensure_resolve_paths():
    """Add DaVinci Resolve scripting module paths to sys.path if not present."""
    ensure_resolve_paths()


def _import_resolve_script():
    """Import DaVinciResolveScript module."""
    module = import_resolve_script()
    if module is None:
        logger.debug("DaVinciResolveScript not found.")
    return module


class ResolveConnection:
    """
    Singleton connection to DaVinci Resolve.
    
    Lazily connects on first use. Provides project, media_pool, timeline references.
    """

    _instance: Optional[ResolveConnection] = None

    def __init__(self):
        self.adapter = None
        self.transport: ResolveTransport | None = None
        self._dvr_script = None
        self.resolve = None
        self.project_manager = None
        self.project = None
        self.media_pool = None
        self.timeline = None
        self.fps: float = 25.0
        self.start_frame: int = 0
        self._disk_db_conn: Optional[sqlite3.Connection] = None
        self._disk_db_conn_path: Optional[str] = None

    @classmethod
    def get(cls) -> ResolveConnection:
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    def connect(self, *, read_project_state: bool = True) -> None:
        """
        Establish connection to DaVinci Resolve.
        
        Raises ResolveNotRunning if DaVinci Resolve is not accessible.
        """
        self.__dict__.pop("activate_project_library_registration", None)
        self.adapter = select_adapter()
        self.transport = self.adapter.transport
        self.resolve = self.adapter.connect()

        if not read_project_state:
            return

        project_manager = self.resolve.GetProjectManager()
        if project_manager is None:
            raise ResolveNotRunning("Connected to DaVinci Resolve but cannot get ProjectManager.")
        self._apply_live_state(self._read_live_state(project_manager=project_manager))
        from .core.owned_resolve_lifecycle import configure_project_library_activation

        if not configure_project_library_activation(self):
            from .core.project_library_gui_activation import configure_project_library_gui_activation

            configure_project_library_gui_activation(self)

        logger.info(
            "Connected to DaVinci Resolve via %s. Project: %s, Timeline: %s, FPS: %s",
            self.transport.value if self.transport else "unknown",
            self.project.GetName() if self.project else "None",
            self.timeline.GetName() if self.timeline else "None",
            self.fps,
        )

    def refresh(self) -> None:
        """
        Refresh all object references.
        
        Call after operations that change state (close project, switch timeline, etc.)
        DaVinci Resolve API objects become stale after such changes.
        """
        if self._disk_db_conn is not None:
            try:
                self._disk_db_conn.close()
            except Exception:
                pass
            self._disk_db_conn = None
            self._disk_db_conn_path = None
        if not self.resolve:
            self.connect()
            return

        self._apply_live_state(self._read_live_state())

    def current_state(self) -> dict[str, Any]:
        """Return a fresh DaVinci Resolve state snapshot and update cached references."""
        if not self.resolve:
            self.connect()
        state = self._read_live_state()
        self._apply_live_state(state)
        return self._public_state(state)

    def wait_for_state(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        *,
        description: str,
        attempts: int = 6,
        delay: float = 0.1,
    ) -> dict[str, Any]:
        """Poll DaVinci Resolve until a predicate matches the fresh live state."""
        last_state: dict[str, Any] | None = None
        for attempt in range(1, attempts + 1):
            state = self.current_state()
            last_state = state
            if predicate(state):
                return state
            if attempt < attempts:
                time.sleep(delay)

        raise APICallFailed(
            f"DaVinci Resolve state did not converge to {description}.",
            details={
                "description": description,
                "last_state": last_state or {},
                "attempts": attempts,
            },
        )

    def _update_fps(self) -> None:
        """Update FPS and start_frame from current timeline."""
        if not self.timeline:
            return

        self.start_frame = 0
        if hasattr(self.timeline, "GetStartFrame"):
            try:
                self.start_frame = int(self.timeline.GetStartFrame())
            except (TypeError, ValueError):
                pass

        try:
            settings = self.timeline.GetSetting()
            if isinstance(settings, dict):
                self.fps = float(settings.get("timelineFrameRate", 25.0))
            else:
                fps_val = self.timeline.GetSetting("timelineFrameRate")
                if fps_val:
                    self.fps = float(fps_val)
        except (TypeError, ValueError):
            self.fps = 25.0

    def _timeline_metrics(self, timeline) -> tuple[float, int]:
        """Read FPS and start frame from a timeline object."""
        fps = 25.0
        start_frame = 0
        if not timeline:
            return fps, start_frame

        if hasattr(timeline, "GetStartFrame"):
            try:
                start_frame = int(timeline.GetStartFrame())
            except (TypeError, ValueError):
                pass

        try:
            settings = timeline.GetSetting()
            if isinstance(settings, dict):
                fps = float(settings.get("timelineFrameRate", 25.0))
            else:
                fps_val = timeline.GetSetting("timelineFrameRate")
                if fps_val:
                    fps = float(fps_val)
        except (TypeError, ValueError):
            fps = 25.0

        return fps, start_frame

    def _read_live_state(self, project_manager=None) -> dict[str, Any]:
        """Read project/timeline state directly from DaVinci Resolve."""
        transport = self.transport.value if self.transport else None

        def read_api(step: str, func: Callable[[], Any]) -> Any:
            try:
                return func()
            except APICallFailed:
                raise
            except Exception as exc:
                raise APICallFailed(
                    "DaVinci Resolve API became unavailable while reading live state.",
                    details={
                        "step": step,
                        "transport": transport,
                        "error": str(exc),
                    },
                ) from exc

        live_project_manager = project_manager or (
            read_api("GetProjectManager", self.resolve.GetProjectManager) if self.resolve else None
        )
        project = read_api("GetCurrentProject", live_project_manager.GetCurrentProject) if live_project_manager else None
        media_pool = read_api("GetMediaPool", project.GetMediaPool) if project else None
        timeline = read_api("GetCurrentTimeline", project.GetCurrentTimeline) if project else None
        fps, start_frame = self._timeline_metrics(timeline)
        timeline_count = None
        if project:
            try:
                timeline_count = project.GetTimelineCount() or 0
            except Exception:
                timeline_count = None
        project_name = read_api("GetProjectName", project.GetName) if project else None
        timeline_name = read_api("GetTimelineName", timeline.GetName) if timeline else None

        return {
            "project_manager": live_project_manager,
            "project": project,
            "media_pool": media_pool,
            "timeline": timeline,
            "project_name": project_name,
            "timeline_name": timeline_name,
            "timeline_count": timeline_count,
            "fps": fps if timeline else None,
            "start_frame": start_frame if timeline else None,
        }

    def _apply_live_state(self, state: dict[str, Any]) -> None:
        """Update cached connection objects from a live state snapshot."""
        self.project_manager = state.get("project_manager")
        self.project = state.get("project")
        self.media_pool = state.get("media_pool")
        self.timeline = state.get("timeline")
        self.fps = float(state.get("fps") or 25.0)
        self.start_frame = int(state.get("start_frame") or 0)

    def _public_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Return the serializable portion of a live state snapshot."""
        return {
            "project": state.get("project_name"),
            "timeline": state.get("timeline_name"),
            "timeline_count": state.get("timeline_count"),
            "fps": state.get("fps"),
            "start_frame": state.get("start_frame"),
        }

    def require_project(self) -> None:
        """Ensure a project is open. Raises NoProjectOpen otherwise."""
        if not self.project:
            # Try refresh first
            self.refresh()
            if not self.project:
                raise NoProjectOpen()

    def require_timeline(self) -> None:
        """Ensure a timeline is active. Raises NoTimelineOpen otherwise."""
        self.require_project()
        if not self.timeline:
            # Try refresh
            self.refresh()
            if not self.timeline:
                raise NoTimelineOpen()

    def disk_db_path(self, *, allow_project_name_inference: bool = True) -> str:
        """Return the on-disk SQLite path for the current project."""
        if not self.project:
            raise NoProjectOpen()

        from .runtime_health import resolve_current_disk_project_db

        details = resolve_current_disk_project_db(
            self,
            allow_project_name_inference=allow_project_name_inference,
        )
        return str(details["project_db_path"])

    def disk_db_connection(self, *, allow_project_name_inference: bool = True) -> sqlite3.Connection:
        """Return a cached sqlite3 connection to the current project's on-disk DB."""
        db_path = self.disk_db_path(allow_project_name_inference=allow_project_name_inference)
        if self._disk_db_conn is None or self._disk_db_conn_path != db_path:
            if self._disk_db_conn is not None:
                try:
                    self._disk_db_conn.close()
                except Exception:
                    pass
            self._disk_db_conn = sqlite3.connect(db_path)
            self._disk_db_conn.row_factory = sqlite3.Row
            self._disk_db_conn_path = db_path
        return self._disk_db_conn

    def disk_db_cursor(self, *, allow_project_name_inference: bool = True) -> sqlite3.Cursor:
        """Return a cursor from the cached sqlite3 connection to the project DB."""
        return self.disk_db_connection(
            allow_project_name_inference=allow_project_name_inference
        ).cursor()

    @property
    def is_connected(self) -> bool:
        return self.resolve is not None

    @property
    def has_project(self) -> bool:
        return self.project is not None

    @property
    def has_timeline(self) -> bool:
        return self.timeline is not None


def get_connection(
    require_project: bool = True,
    require_timeline: bool = False,
    read_project_state: bool = True,
) -> ResolveConnection:
    """
    Get a connected DaVinci ResolveConnection.
    
    Convenience function for CLI commands.
    """
    conn = ResolveConnection.get()
    if not conn.is_connected:
        conn.connect(read_project_state=read_project_state)
    if require_project:
        conn.require_project()
    if require_timeline:
        conn.require_timeline()
    if os.environ.get("CUTAGENT_SDK_TIMELINE_GUARD"):
        # SDK caption/transcript dispatches carry the exact snapshot guard into
        # the CutAgent CLI process. Validate it after this process acquires its
        # own DaVinci Resolve references and before the command can read, render,
        # bill, or mutate the active timeline.
        from .core import timeline_ops

        timeline_ops.require_sdk_marker_mutation_guard(conn)
    return conn
