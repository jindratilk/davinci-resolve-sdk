"""Exact-PID macOS Accessibility primitives for Project Manager libraries."""

from __future__ import annotations

import ctypes
import os
import time
from pathlib import Path
from typing import Any


_UTF8 = 0x08000100
_AX_POINT = 1
_CF_NUMBER_DOUBLE = 13
_ADD_DIALOG_TITLE = "Create New Project Library"
_NEW_PROJECT_DIALOG_TITLE = "Create New Project"


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _Size(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class _Rect(ctypes.Structure):
    _fields_ = [("origin", _Point), ("size", _Size)]


class _AX:
    def __init__(self) -> None:
        self.cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.ax = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        self.cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        self.cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        self.cf.CFStringGetCString.restype = ctypes.c_bool
        self.cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        self.cf.CFStringGetTypeID.restype = ctypes.c_ulong
        self.cf.CFNumberGetTypeID.restype = ctypes.c_ulong
        self.cf.CFNumberGetValue.restype = ctypes.c_bool
        self.cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        self.cf.CFNumberCreate.restype = ctypes.c_void_p
        self.cf.CFNumberCreate.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        self.cf.CFGetTypeID.restype = ctypes.c_ulong
        self.cf.CFGetTypeID.argtypes = [ctypes.c_void_p]
        self.cf.CFEqual.restype = ctypes.c_bool
        self.cf.CFEqual.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.cf.CFArrayGetCount.restype = ctypes.c_long
        self.cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
        self.cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
        self.cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
        self.cf.CFBooleanGetValue.restype = ctypes.c_bool
        self.cf.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
        self.cf.CFRetain.restype = ctypes.c_void_p
        self.cf.CFRetain.argtypes = [ctypes.c_void_p]
        self.cf.CFRelease.argtypes = [ctypes.c_void_p]
        self.ax.AXIsProcessTrusted.restype = ctypes.c_bool
        self.ax.AXUIElementCreateApplication.restype = ctypes.c_void_p
        self.ax.AXUIElementCreateApplication.argtypes = [ctypes.c_int]
        self.ax.AXUIElementGetPid.restype = ctypes.c_int
        self.ax.AXUIElementGetPid.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        self.ax.AXUIElementCopyAttributeValue.restype = ctypes.c_int
        self.ax.AXUIElementCopyAttributeValue.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
        ]
        self.ax.AXUIElementSetAttributeValue.restype = ctypes.c_int
        self.ax.AXUIElementSetAttributeValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        self.ax.AXUIElementPerformAction.restype = ctypes.c_int
        self.ax.AXUIElementPerformAction.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.ax.AXValueGetType.restype = ctypes.c_int
        self.ax.AXValueGetType.argtypes = [ctypes.c_void_p]
        self.ax.AXValueGetValue.restype = ctypes.c_bool
        self.ax.AXValueGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        self.ax._AXUIElementGetWindow.restype = ctypes.c_int
        self.ax._AXUIElementGetWindow.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]

    def _string_ref(self, value: str) -> int:
        ref = self.cf.CFStringCreateWithCString(None, value.encode("utf-8"), _UTF8)
        if not ref:
            raise RuntimeError("macOS could not allocate an Accessibility string")
        return int(ref)

    def release(self, value: int | None) -> None:
        if value:
            self.cf.CFRelease(value)

    def _copy(self, element: int, attribute: str) -> int | None:
        key = self._string_ref(attribute)
        output = ctypes.c_void_p()
        try:
            error = self.ax.AXUIElementCopyAttributeValue(element, key, ctypes.byref(output))
        finally:
            self.release(key)
        return int(output.value) if error == 0 and output.value else None

    def string(self, element: int, attribute: str) -> str:
        value = self._copy(element, attribute)
        if not value:
            return ""
        try:
            if self.cf.CFGetTypeID(value) != self.cf.CFStringGetTypeID():
                return ""
            buffer = ctypes.create_string_buffer(8192)
            if not self.cf.CFStringGetCString(value, buffer, len(buffer), _UTF8):
                return ""
            return buffer.value.decode("utf-8")
        finally:
            self.release(value)

    def boolean(self, element: int, attribute: str) -> bool:
        value = self._copy(element, attribute)
        if not value:
            return False
        try:
            return bool(self.cf.CFBooleanGetValue(value))
        finally:
            self.release(value)

    def scalar_text(self, element: int, attribute: str = "AXValue") -> str:
        value = self._copy(element, attribute)
        if not value:
            return ""
        try:
            value_type = self.cf.CFGetTypeID(value)
            if value_type == self.cf.CFStringGetTypeID():
                buffer = ctypes.create_string_buffer(8192)
                if self.cf.CFStringGetCString(value, buffer, len(buffer), _UTF8):
                    return buffer.value.decode("utf-8")
                return ""
            if value_type == self.cf.CFNumberGetTypeID():
                numeric = ctypes.c_double()
                if self.cf.CFNumberGetValue(value, _CF_NUMBER_DOUBLE, ctypes.byref(numeric)):
                    return f"{numeric.value:.15g}"
            return ""
        finally:
            self.release(value)

    def point(self, element: int) -> tuple[float, float] | None:
        value = self._copy(element, "AXPosition")
        if not value:
            return None
        try:
            point = _Point()
            if self.ax.AXValueGetType(value) != _AX_POINT:
                return None
            if not self.ax.AXValueGetValue(value, _AX_POINT, ctypes.byref(point)):
                return None
            return point.x, point.y
        finally:
            self.release(value)

    def size(self, element: int) -> tuple[float, float] | None:
        value = self._copy(element, "AXSize")
        if not value:
            return None
        try:
            size = _Size()
            if self.ax.AXValueGetType(value) != 2:
                return None
            if not self.ax.AXValueGetValue(value, 2, ctypes.byref(size)):
                return None
            return size.width, size.height
        finally:
            self.release(value)

    def window_id(self, element: int) -> int:
        output = ctypes.c_uint32()
        if self.ax._AXUIElementGetWindow(element, ctypes.byref(output)) != 0 or output.value <= 0:
            raise RuntimeError("the exact Accessibility window has no CoreGraphics identity")
        return int(output.value)

    def pid(self, element: int) -> int:
        output = ctypes.c_int()
        if self.ax.AXUIElementGetPid(element, ctypes.byref(output)) != 0 or output.value <= 0:
            raise RuntimeError("the exact Accessibility element has no process identity")
        return int(output.value)

    def _array(self, element: int, attribute: str) -> list[int]:
        value = self._copy(element, attribute)
        if not value:
            return []
        try:
            output: list[int] = []
            for index in range(self.cf.CFArrayGetCount(value)):
                child = self.cf.CFArrayGetValueAtIndex(value, index)
                if child:
                    self.cf.CFRetain(child)
                    output.append(int(child))
            return output
        finally:
            self.release(value)

    def windows(self, pid: int) -> list[int]:
        application = self.ax.AXUIElementCreateApplication(pid)
        if not application:
            return []
        try:
            return self._array(int(application), "AXWindows")
        finally:
            self.release(int(application))

    def window(self, pid: int, title: str) -> int:
        windows = self.windows(pid)
        matches = [window for window in windows if self.string(window, "AXTitle") == title]
        if len(matches) != 1:
            for window in windows:
                self.release(window)
            raise RuntimeError(f"{title} window is unavailable or ambiguous")
        selected = matches[0]
        for window in windows:
            if window != selected:
                self.release(window)
        return selected

    def flatten(self, root: int, *, label: str, max_elements: int = 1000) -> list[int]:
        queue = [root]
        output: list[int] = []
        while queue and len(output) < max_elements:
            current = queue.pop(0)
            output.append(current)
            queue.extend(self._array(current, "AXChildren"))
        if queue:
            for element in queue:
                self.release(element)
            for element in output:
                self.release(element)
            raise RuntimeError(f"{label} Accessibility tree exceeds the safe bound")
        return output

    def flatten_window(self, pid: int, title: str, *, max_elements: int = 1000) -> list[int]:
        return self.flatten(self.window(pid, title), label=title, max_elements=max_elements)

    def project_manager_items(self, pid: int) -> list[int]:
        windows = self.windows(pid)
        titled = [window for window in windows if self.string(window, "AXTitle") == "Project Manager"]
        if len(titled) == 1:
            selected = titled[0]
        elif len(windows) == 1:
            selected = windows[0]
        else:
            self.release_all(windows)
            raise RuntimeError("the exact Resolve PID does not expose one unambiguous AX window")
        for window in windows:
            if window != selected:
                self.release(window)
        items = self.flatten(selected, label="Project Manager")
        if not (
            self.exact(items, "Show/Hide Project Libraries", {"AXCheckBox"})
            or self.exact(items, "Add Project Library", {"AXButton"})
        ):
            self.release_all(items)
            raise RuntimeError("the exact AX window is not in Project Manager state")
        return items

    def open_project_manager(self, pid: int) -> None:
        application = self.ax.AXUIElementCreateApplication(pid)
        if not application:
            raise RuntimeError("the exact Resolve PID has no Accessibility application")
        items = self.flatten(int(application), label="Resolve application", max_elements=4000)
        try:
            matches = [
                element for element in self.exact(items, "Project Manager", {"AXButton"})
            ]
            if len(matches) != 1:
                raise RuntimeError("Project Manager window button is unavailable or ambiguous")
            element_window_id = self.window_id(matches[0])
            windows = self.windows(pid)
            try:
                titles = [
                    self.string(window, "AXTitle")
                    for window in windows
                    if self.window_id(window) == element_window_id
                ]
                if len(titles) != 1 or not titles[0]:
                    raise RuntimeError("Project Manager button window is unavailable or ambiguous")
                _owned_action(self, matches[0], "AXPress", pid=pid, window_title=titles[0])
            finally:
                self.release_all(windows)
        finally:
            self.release_all(items)

    def release_all(self, elements: list[int]) -> None:
        for element in elements:
            self.release(element)

    def label(self, element: int) -> str:
        for attribute in ("AXTitle", "AXDescription", "AXValue"):
            value = self.string(element, attribute)
            if value:
                return value
        return ""

    def exact(self, elements: list[int], label: str, roles: set[str]) -> list[int]:
        return [
            element for element in elements
            if self.string(element, "AXRole") in roles and self.label(element) == label
        ]

    def press(self, element: int) -> None:
        self.action(element, "AXPress")

    def action(self, element: int, name: str) -> None:
        action = self._string_ref(name)
        try:
            if self.ax.AXUIElementPerformAction(element, action) != 0:
                raise RuntimeError(f"macOS Accessibility {name} failed")
        finally:
            self.release(action)

    def parent(self, element: int) -> int:
        parent = self._copy(element, "AXParent")
        if not parent:
            raise RuntimeError("the exact Accessibility control has no parent")
        return parent

    def belongs_to(self, element: int, ancestor: int, *, max_depth: int = 64) -> bool:
        """Prove an AX control is contained by the expected titled window."""

        if self.cf.CFEqual(element, ancestor):
            return True
        current = self._copy(element, "AXParent")
        depth = 0
        try:
            while current and depth < max_depth:
                if self.cf.CFEqual(current, ancestor):
                    return True
                parent = self._copy(current, "AXParent")
                self.release(current)
                current = parent
                depth += 1
            return False
        finally:
            self.release(current)

    def set_string(self, element: int, value: str) -> None:
        attribute = self._string_ref("AXValue")
        requested = self._string_ref(value)
        try:
            if self.ax.AXUIElementSetAttributeValue(element, attribute, requested) != 0:
                raise RuntimeError("macOS Accessibility field write failed")
        finally:
            self.release(requested)
            self.release(attribute)

    def set_number(self, element: int, value: float) -> None:
        attribute = self._string_ref("AXValue")
        numeric = ctypes.c_double(float(value))
        requested = self.cf.CFNumberCreate(None, _CF_NUMBER_DOUBLE, ctypes.byref(numeric))
        if not requested:
            self.release(attribute)
            raise RuntimeError("macOS could not allocate an Accessibility number")
        try:
            if self.ax.AXUIElementSetAttributeValue(element, attribute, requested) != 0:
                raise RuntimeError("macOS Accessibility numeric field write failed")
        finally:
            self.release(int(requested))
            self.release(attribute)


def show_project_manager(pid: int) -> dict[str, Any]:
    client = _AX()
    if not client.ax.AXIsProcessTrusted():
        raise PermissionError("macOS Accessibility is not authorized")
    try:
        items = client.project_manager_items(pid)
    except RuntimeError:
        client.open_project_manager(pid)
        time.sleep(0.5)
        items = client.project_manager_items(pid)
    client.release_all(items)
    return {"ok": True, "pid": pid, "route": "project_manager_prepare"}


def inspect_accessibility(pid: int) -> dict[str, Any]:
    client = _AX()
    if not client.ax.AXIsProcessTrusted():
        raise PermissionError("macOS Accessibility is not authorized")
    windows = client.windows(pid)
    try:
        if not windows:
            raise RuntimeError("the exact Resolve PID has no accessible windows")
        return {"ok": True, "pid": pid, "windowCount": len(windows)}
    finally:
        client.release_all(windows)


def create_project_via_project_manager(pid: int, *, name: str) -> dict[str, Any]:
    """Create the first project in an exact owned GUI's fresh Disk library."""
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise RuntimeError("the requested bootstrap project name is invalid")
    client = _AX()
    if not client.ax.AXIsProcessTrusted():
        raise PermissionError("macOS Accessibility is not authorized")
    _dismiss_software_update(client, pid=pid)
    items = client.project_manager_items(pid)
    try:
        buttons = client.exact(items, "New Project", {"AXButton"})
        if len(buttons) != 1:
            raise RuntimeError("New Project button is unavailable or ambiguous")
        _owned_action(client, buttons[0], "AXPress", pid=pid, window_title="Project Manager")
    finally:
        client.release_all(items)

    time.sleep(0.5)
    dialog = client.flatten_window(pid, _NEW_PROJECT_DIALOG_TITLE)
    try:
        fields = [element for element in dialog if client.string(element, "AXRole") == "AXTextField"]
        name_fields = [element for element in fields if not Path(client.string(element, "AXValue")).is_absolute()]
        create_buttons = client.exact(dialog, "Create", {"AXButton"})
        if len(name_fields) != 1 or len(create_buttons) != 1:
            raise RuntimeError("Create New Project controls are unavailable or ambiguous")
        _assert_owned_element_window(
            client,
            name_fields[0],
            pid=pid,
            window_title=_NEW_PROJECT_DIALOG_TITLE,
        )
        client.set_string(name_fields[0], name)
        if client.string(name_fields[0], "AXValue") != name:
            raise RuntimeError("Create New Project name field did not preserve the exact value")
        time.sleep(0.25)
        _click(client, create_buttons[0], pid=pid, window_title=_NEW_PROJECT_DIALOG_TITLE)
    finally:
        client.release_all(dialog)
    return {"ok": True, "pid": pid, "route": "project_manager_create", "name": name}


def _core_graphics_window(window_id: int) -> dict[str, Any]:
    if window_id <= 0:
        raise RuntimeError("the Accessibility window has no safe CoreGraphics identity")
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    cg.CGRectMakeWithDictionaryRepresentation.restype = ctypes.c_bool
    cg.CGRectMakeWithDictionaryRepresentation.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Rect)]
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    cf.CFNumberGetValue.restype = ctypes.c_bool
    cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    cf.CFBooleanGetValue.restype = ctypes.c_bool
    cf.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    cf.CFRelease.argtypes = [ctypes.c_void_p]

    keys = {
        name: ctypes.c_void_p.in_dll(cg, name).value
        for name in (
            "kCGWindowNumber",
            "kCGWindowOwnerPID",
            "kCGWindowName",
            "kCGWindowIsOnscreen",
            "kCGWindowAlpha",
            "kCGWindowBounds",
        )
    }

    def value(row: int, name: str) -> int | None:
        result = cf.CFDictionaryGetValue(row, keys[name])
        return int(result) if result else None

    def number(row: int, name: str, *, kind: int) -> int | float | None:
        raw = value(row, name)
        if raw is None:
            return None
        output: ctypes.c_longlong | ctypes.c_double
        output = ctypes.c_double() if kind == 13 else ctypes.c_longlong()
        if not cf.CFNumberGetValue(raw, kind, ctypes.byref(output)):
            return None
        return output.value

    def string(row: int, name: str) -> str:
        raw = value(row, name)
        if raw is None:
            return ""
        buffer = ctypes.create_string_buffer(8192)
        if not cf.CFStringGetCString(raw, buffer, len(buffer), _UTF8):
            return ""
        return buffer.value.decode("utf-8")

    rows = cg.CGWindowListCopyWindowInfo(1 << 3, window_id)
    if not rows:
        raise RuntimeError("CoreGraphics window ownership is unavailable")
    try:
        matched: dict[str, Any] | None = None
        for index in range(cf.CFArrayGetCount(rows)):
            row = cf.CFArrayGetValueAtIndex(rows, index)
            if not row or number(row, "kCGWindowNumber", kind=4) != window_id:
                continue
            if matched is not None:
                raise RuntimeError("the Accessibility window has ambiguous CoreGraphics matches")
            bounds_ref = value(row, "kCGWindowBounds")
            bounds = _Rect()
            if not bounds_ref or not cg.CGRectMakeWithDictionaryRepresentation(bounds_ref, ctypes.byref(bounds)):
                raise RuntimeError("CoreGraphics window ownership is malformed")
            onscreen_ref = value(row, "kCGWindowIsOnscreen")
            matched = {
                "window_id": window_id,
                "owner_pid": number(row, "kCGWindowOwnerPID", kind=4),
                "title": string(row, "kCGWindowName"),
                "onscreen": bool(cf.CFBooleanGetValue(onscreen_ref)) if onscreen_ref else False,
                "alpha": number(row, "kCGWindowAlpha", kind=13),
                "bounds": {
                    "x": bounds.origin.x,
                    "y": bounds.origin.y,
                    "width": bounds.size.width,
                    "height": bounds.size.height,
                },
            }
        if matched is not None:
            return matched
    finally:
        cf.CFRelease(rows)
    raise RuntimeError("the Accessibility window has no CoreGraphics match")


def _assert_owned_element_window(
    client: _AX, element: int, *, pid: int, window_title: str
) -> tuple[tuple[float, float], tuple[float, float], int]:
    window = client.window(pid, window_title)
    try:
        window_id = client.window_id(window)
        window_pid = client.pid(window)
        element_pid = client.pid(element)
        element_belongs_to_window = client.belongs_to(element, window)
        position = client.point(window)
        size = client.size(window)
        element_position = client.point(element)
        element_size = client.size(element)
    finally:
        client.release(window)
    if not element_belongs_to_window:
        raise RuntimeError("the exact Accessibility control is outside its bound AX window hierarchy")
    if window_pid != pid or element_pid != pid:
        raise RuntimeError("the exact Accessibility control belongs to a different process")
    if position is None or size is None or size[0] <= 0 or size[1] <= 0:
        raise RuntimeError(f"{window_title} Accessibility window has no safe geometry")
    if (
        element_position is None
        or element_size is None
        or element_size[0] <= 0
        or element_size[1] <= 0
        or not _geometry_contains((*position, *size), (*element_position, *element_size))
    ):
        raise RuntimeError("the exact Accessibility control is outside its bound window")
    _assert_owned_cg_window(
        window_id,
        pid=pid,
        expected_title=window_title,
        expected_geometry=(*position, *size),
    )
    return position, size, window_id


def _geometry_contains(
    outer: tuple[float, float, float, float],
    inner: tuple[float, float, float, float],
    *,
    tolerance: float = 2.0,
) -> bool:
    left, top, width, height = outer
    x, y, inner_width, inner_height = inner
    return (
        left - tolerance <= x < x + inner_width <= left + width + tolerance
        and top - tolerance <= y < y + inner_height <= top + height + tolerance
    )


def _assert_owned_cg_window(
    window_id: int,
    *,
    pid: int,
    expected_title: str | None = None,
    expected_geometry: tuple[float, float, float, float] | None = None,
    contained_geometry: tuple[float, float, float, float] | None = None,
) -> None:
    metadata = _core_graphics_window(window_id)
    bounds = metadata.get("bounds")
    if (
        metadata.get("window_id") != window_id
        or metadata.get("owner_pid") != pid
        or (expected_title is not None and metadata.get("title") != expected_title)
        or metadata.get("onscreen") is not True
        or not isinstance(metadata.get("alpha"), (int, float))
        or metadata["alpha"] <= 0
        or not isinstance(bounds, dict)
    ):
        raise RuntimeError("the exact Accessibility window is not owned by the selected process")
    observed = (bounds.get("x"), bounds.get("y"), bounds.get("width"), bounds.get("height"))
    if any(not isinstance(value, (int, float)) for value in observed):
        raise RuntimeError("the CoreGraphics window geometry is malformed")
    if expected_geometry is not None and any(
        abs(float(left) - float(right)) > 2.0 for left, right in zip(expected_geometry, observed)
    ):
        raise RuntimeError("the Accessibility and CoreGraphics window geometries disagree")
    if contained_geometry is not None:
        if not _geometry_contains(tuple(float(value) for value in observed), contained_geometry):
            raise RuntimeError("the Accessibility control geometry is outside its owned CoreGraphics window")


def _owned_action(
    client: _AX, element: int, name: str, *, pid: int, window_title: str
) -> None:
    _assert_owned_element_window(client, element, pid=pid, window_title=window_title)
    client.action(element, name)


def _click(client: _AX, element: int, *, pid: int, window_title: str) -> None:
    from .magic_mask_gui_route import Rect, _post_mouse_drag

    position = client.point(element)
    size = client.size(element)
    if position is None or size is None or size[0] <= 0 or size[1] <= 0:
        raise RuntimeError("the exact Accessibility control has no safe geometry")
    window_position, window_size, window_id = _assert_owned_element_window(
        client, element, pid=pid, window_title=window_title
    )
    element_left, element_top = position
    element_right = element_left + size[0]
    element_bottom = element_top + size[1]
    window_left, window_top = window_position
    window_right = window_left + window_size[0]
    window_bottom = window_top + window_size[1]
    if not (
        window_left <= element_left < element_right <= window_right
        and window_top <= element_top < element_bottom <= window_bottom
    ):
        raise RuntimeError("the exact Accessibility control is outside its bound window")
    point = (
        int(round(position[0] + size[0] / 2.0)),
        int(round(position[1] + size[1] / 2.0)),
    )
    _post_mouse_drag(
        [point, point],
        target_pid=pid,
        target_window_id=window_id,
        target_window_rect=Rect(
            x=int(round(window_position[0])),
            y=int(round(window_position[1])),
            width=int(round(window_size[0])),
            height=int(round(window_size[1])),
        ),
    )


def _dismiss_software_update(client: _AX, *, pid: int) -> bool:
    try:
        items = client.flatten_window(pid, "Software Update", max_elements=1000)
    except RuntimeError:
        return False
    try:
        skip = client.exact(items, "Skip", {"AXButton"})
        if len(skip) != 1:
            raise RuntimeError("Software Update Skip button is unavailable or ambiguous")
        _click(client, skip[0], pid=pid, window_title="Software Update")
    finally:
        client.release_all(items)
    time.sleep(0.5)
    return True


def _select_directory(client: _AX, *, pid: int, root: Path) -> None:
    if not root.is_absolute() or not root.is_dir():
        raise RuntimeError("the requested Project Library directory is unavailable")
    chooser = client.flatten_window(pid, "Select a directory", max_elements=4000)
    try:
        documents = Path(os.environ.get("HOME", "")) / "Documents"
        try:
            components = root.relative_to(documents).parts
            anchor_label = "Documents"
        except ValueError:
            components = root.parts[1:]
            anchor_label = "Macintosh HD"
        anchors = client.exact(chooser, anchor_label, {"AXStaticText"})
        if len(anchors) != 1:
            raise RuntimeError("the file chooser path anchor is unavailable or ambiguous")
        _click(client, anchors[0], pid=pid, window_title="Select a directory")
        cell = client.parent(anchors[0])
        try:
            if client.string(cell, "AXRole") != "AXCell":
                raise RuntimeError("the file chooser path anchor has an unsafe role")
            _assert_owned_element_window(client, cell, pid=pid, window_title="Select a directory")
            try:
                client.action(cell, "AXOpen")
            except RuntimeError:
                # AppKit may return kAXErrorCannotComplete after dispatch. The
                # next exact component readback below is the authority.
                pass
        finally:
            client.release(cell)
    finally:
        client.release_all(chooser)
    time.sleep(0.25)

    for component in components:
        opened = False
        for _page in range(8):
            chooser = client.flatten_window(pid, "Select a directory", max_elements=4000)
            try:
                rows = client.exact(chooser, component, {"AXTextField"})
                if len(rows) > 1:
                    raise RuntimeError(f"file chooser path component is ambiguous: {component}")
                if len(rows) == 1:
                    _click(client, rows[0], pid=pid, window_title="Select a directory")
                    _assert_owned_element_window(
                        client, rows[0], pid=pid, window_title="Select a directory"
                    )
                    try:
                        client.action(rows[0], "AXOpen")
                    except RuntimeError:
                        # Require the following directory component to prove the open.
                        pass
                    opened = True
                    break
                scroll_areas = [
                    element for element in chooser
                    if client.string(element, "AXRole") == "AXScrollArea" and (client.size(element) or (0, 0))[0] > 300
                ]
                if len(scroll_areas) != 1:
                    break
                _assert_owned_element_window(
                    client, scroll_areas[0], pid=pid, window_title="Select a directory"
                )
                try:
                    client.action(scroll_areas[0], "AXScrollDownByPage")
                except RuntimeError:
                    pass
            finally:
                client.release_all(chooser)
            time.sleep(0.05)
        if not opened:
            raise RuntimeError(f"file chooser path component is unavailable: {component}")
        time.sleep(0.15)

    chooser = client.flatten_window(pid, "Select a directory", max_elements=4000)
    try:
        where = [
            element
            for element in chooser
            if client.string(element, "AXRole") == "AXPopUpButton"
            and client.string(element, "AXIdentifier") == "where popup"
        ]
        if len(where) != 1 or client.string(where[0], "AXValue") != root.name:
            raise RuntimeError("the file chooser did not expose one exact current-directory control")
        _owned_action(client, where[0], "AXPress", pid=pid, window_title="Select a directory")
    finally:
        client.release_all(chooser)
    time.sleep(0.25)

    chooser = client.flatten_window(pid, "Select a directory", max_elements=4000)
    try:
        menu_items = [element for element in chooser if client.string(element, "AXRole") == "AXMenuItem"]
        hierarchy: list[int] = []
        for element in menu_items:
            if client.string(element, "AXIdentifier") != "retargetFromMenuItem:" or not client.label(element):
                break
            hierarchy.append(element)
        expected = list(reversed(root.resolve(strict=True).parts[1:]))
        actual = [client.label(element) for element in hierarchy]
        # AppKit appends exactly two non-path entries after the absolute local
        # path: the volume and the computer. Requiring the whole leading menu
        # prevents a different path whose suffix merely resembles ``root``.
        exact_directory = len(actual) == len(expected) + 2 and actual[: len(expected)] == expected
        if hierarchy:
            # Selecting the already-current first item safely dismisses the
            # path menu without changing the chooser directory.
            _owned_action(client, hierarchy[0], "AXPress", pid=pid, window_title="Select a directory")
        if not exact_directory:
            raise RuntimeError("the file chooser did not prove the exact requested directory hierarchy")
    finally:
        client.release_all(chooser)
    time.sleep(0.25)

    chooser = client.flatten_window(pid, "Select a directory", max_elements=4000)
    try:
        buttons = client.exact(chooser, "Open", {"AXButton"})
        if len(buttons) != 1:
            raise RuntimeError("file chooser Open button is unavailable or ambiguous")
        _owned_action(client, buttons[0], "AXPress", pid=pid, window_title="Select a directory")
    finally:
        client.release_all(chooser)
    time.sleep(0.5)


def connect_project_library(pid: int, *, name: str, root: Path) -> dict[str, Any]:
    client = _AX()
    if not client.ax.AXIsProcessTrusted():
        raise PermissionError("macOS Accessibility is not authorized")
    try:
        items = client.project_manager_items(pid)
    except RuntimeError:
        client.open_project_manager(pid)
        time.sleep(0.5)
        items = client.project_manager_items(pid)
    try:
        add = client.exact(items, "Add Project Library", {"AXButton"})
        if not add:
            toggles = client.exact(items, "Show/Hide Project Libraries", {"AXCheckBox"})
            if len(toggles) != 1:
                raise RuntimeError("project libraries disclosure is unavailable or ambiguous")
            _click(client, toggles[0], pid=pid, window_title="Project Manager")
            time.sleep(0.5)
            client.release_all(items)
            items = client.project_manager_items(pid)
            add = client.exact(items, "Add Project Library", {"AXButton"})
        if len(add) != 1:
            raise RuntimeError("Add Project Library is unavailable or ambiguous")
        _owned_action(client, add[0], "AXPress", pid=pid, window_title="Project Manager")
    finally:
        client.release_all(items)

    time.sleep(0.5)
    dialog = client.flatten_window(pid, _ADD_DIALOG_TITLE)
    try:
        tabs = client.exact(dialog, "Connect", {"AXCheckBox", "AXRadioButton", "AXTab"})
        if len(tabs) != 1:
            raise RuntimeError("Connect tab is unavailable or ambiguous")
        _click(client, tabs[0], pid=pid, window_title=_ADD_DIALOG_TITLE)
        time.sleep(0.25)
    finally:
        client.release_all(dialog)

    dialog = client.flatten_window(pid, _ADD_DIALOG_TITLE)
    try:
        fields = [element for element in dialog if client.string(element, "AXRole") == "AXTextField"]
        browse = client.exact(dialog, "Browse", {"AXButton"})
        if len(fields) != 1 or len(browse) != 1:
            raise RuntimeError("Connect name field or directory browser is unavailable or ambiguous")
        _assert_owned_element_window(client, fields[0], pid=pid, window_title=_ADD_DIALOG_TITLE)
        client.set_string(fields[0], name)
        if client.string(fields[0], "AXValue") != name:
            raise RuntimeError("Connect name field did not preserve the exact requested value")
        _owned_action(client, browse[0], "AXPress", pid=pid, window_title=_ADD_DIALOG_TITLE)
    finally:
        client.release_all(dialog)

    time.sleep(0.5)
    _select_directory(client, pid=pid, root=root)
    dialog = client.flatten_window(pid, _ADD_DIALOG_TITLE)
    try:
        buttons = client.exact(dialog, "Connect", {"AXButton"})
        if len(buttons) != 1:
            raise RuntimeError("final Connect button is unavailable or ambiguous")
        _owned_action(client, buttons[0], "AXPress", pid=pid, window_title=_ADD_DIALOG_TITLE)
        return {"ok": True, "pid": pid, "route": "project_manager_connect", "fieldCount": 1}
    finally:
        client.release_all(dialog)
