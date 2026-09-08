"""Split implementation for podcast audio activity planning."""

from __future__ import annotations

from types import ModuleType
from typing import Any

from .. import waveform_sync as waveform_sync

from . import common as common
from . import parsing as parsing
from . import levels as levels
from . import normalization as normalization
from . import windows as windows
from . import plan_v1 as plan_v1
from . import plan_v2 as plan_v2
from . import api as api
from . import calibration as calibration

_MODULES: tuple[ModuleType, ...] = (
    common,
    parsing,
    levels,
    normalization,
    windows,
    plan_v1,
    plan_v2,
    api,
    calibration,
)

def _collect_namespace() -> dict[str, Any]:
    namespace: dict[str, Any] = {"waveform_sync": waveform_sync}
    for module in _MODULES:
        for name in getattr(module, "__all__", ()):
            namespace[name] = getattr(module, name)
    return namespace


def _wire_namespace(namespace: dict[str, Any]) -> None:
    for module in _MODULES:
        module.__dict__.update(namespace)


_namespace = _collect_namespace()
_wire_namespace(_namespace)
globals().update(_namespace)
__all__ = tuple(_namespace)
