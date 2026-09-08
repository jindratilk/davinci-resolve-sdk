from __future__ import annotations

from typing import Any, Callable, Optional


def _get_callable(target: Any, name: str) -> Optional[Callable[..., Any]]:
    """Return an API method only when the attribute exists and is callable."""
    if target is None:
        return None
    method = getattr(target, name, None)
    return method if callable(method) else None


def _sleep(seconds: float) -> None:
    from .. import render_engine as facade

    facade.time.sleep(seconds)

