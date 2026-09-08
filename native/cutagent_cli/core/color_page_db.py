"""DB-backed Color Page operations for DaVinci Resolve.

Compatibility facade for the split implementation in
``cutagent_cli.core._color_page_db``. Public imports and legacy tests may still
patch symbols on this module; wrappers synchronize those symbols into the
internal modules before dispatch.
"""

from __future__ import annotations

import inspect as _inspect
from functools import wraps as _wraps

from . import _color_page_db as _impl
from ._color_page_db import *  # noqa: F401,F403


def _make_compat_wrapper(_name: str, _func):
    @_wraps(_func)
    def _wrapped(*args, **kwargs):
        _impl.sync_from_facade(globals())
        return getattr(_impl, _name)(*args, **kwargs)

    return _wrapped


for _name in tuple(getattr(_impl, "__all__", ())):
    if _name == "sync_from_facade":
        continue
    _value = globals().get(_name)
    if _inspect.isfunction(_value):
        globals()[_name] = _make_compat_wrapper(_name, _value)

__all__ = tuple(name for name in getattr(_impl, "__all__", ()) if name != "sync_from_facade")

del _inspect, _make_compat_wrapper, _name, _value
