"""Internal Color Page DB implementation package.

The public compatibility module is ``cutagent_cli.core.color_page_db``.
This package keeps the formerly monolithic implementation split by domain while
allowing the facade to synchronize monkeypatched legacy symbols before calls.
"""

from __future__ import annotations

from types import ModuleType
from typing import Any

from . import constants as constants
from . import proto_codec as proto_codec
from . import version_body as version_body
from . import transforms as transforms
from . import params as params
from . import proto_sections as proto_sections
from . import curves as curves
from . import curve_injections as curve_injections
from . import hdr as hdr
from . import node_graph as node_graph
from . import power_windows as power_windows
from . import cst_hsv as cst_hsv
from . import grade_state as grade_state
from . import mutations_color as mutations_color
from . import mutations_hsv_key as mutations_hsv_key
from . import mutations_node_graph as mutations_node_graph
from . import mutations_nodes as mutations_nodes
from . import mutations_curves as mutations_curves
from . import mutations_cst as mutations_cst
from . import mutations_power_windows as mutations_power_windows
from . import snapshot as snapshot
from . import color_slice as color_slice
from . import color_warper as color_warper

_MODULES: tuple[ModuleType, ...] = (
    constants,
    proto_codec,
    version_body,
    transforms,
    params,
    proto_sections,
    curves,
    curve_injections,
    hdr,
    node_graph,
    power_windows,
    cst_hsv,
    grade_state,
    mutations_color,
    mutations_hsv_key,
    mutations_node_graph,
    mutations_nodes,
    mutations_curves,
    mutations_cst,
    mutations_power_windows,
    snapshot,
    color_slice,
    color_warper,
)

def _module_exports(module: ModuleType) -> list[str]:
    return list(getattr(module, "__all__", ()))


def _collect_namespace() -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    for module in _MODULES:
        for name in _module_exports(module):
            namespace[name] = getattr(module, name)
    for mutable_name in (
        "execute_sqlite_disk_db_mutation",
        "DiskDbMutationSession",
        "find_ti_item_row",
    ):
        namespace[mutable_name] = getattr(params, mutable_name)
    return namespace


def _wire_namespace(namespace: dict[str, Any]) -> None:
    for module in _MODULES:
        module.__dict__.update(namespace)


def sync_from_facade(facade_globals: dict[str, Any]) -> None:
    """Copy monkeypatched compatibility symbols into implementation modules."""
    namespace = _collect_namespace()
    for name in list(namespace):
        if name in facade_globals:
            namespace[name] = facade_globals[name]
    for mutable_name in (
        "execute_sqlite_disk_db_mutation",
        "DiskDbMutationSession",
        "find_ti_item_row",
    ):
        if mutable_name in facade_globals:
            namespace[mutable_name] = facade_globals[mutable_name]
    _wire_namespace(namespace)


_namespace = _collect_namespace()
_wire_namespace(_namespace)
globals().update(_namespace)
__all__ = tuple(_namespace) + ("sync_from_facade",)
