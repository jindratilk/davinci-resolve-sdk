"""Version checks for documented native API additions."""
from typing import Any


def at_least(conn: Any, major: int, minor: int) -> bool:
    getter = getattr(getattr(conn, "resolve", None), "GetVersion", None)
    if not callable(getter):
        return False
    try:
        version = getter()
        return (int(version[0]), int(version[1])) >= (major, minor)
    except (TypeError, ValueError, IndexError, KeyError):
        return False
