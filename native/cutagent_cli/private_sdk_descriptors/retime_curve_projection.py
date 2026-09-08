"""Public curve coordinates, independent of native payload representations."""
from __future__ import annotations

from typing import Any, Mapping

from ..core.retime_curve_readback import curve_coordinates


def exact_curve(target: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    return {"timelineItemId": target["id"], **curve_coordinates(
        state, record_start=target["recordRange"]["start"], source_start=target.get("sourceOriginFrame", target["sourceRange"]["start"]),
    )}


def exact_curves(targets: list[Mapping[str, Any]], states: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]] | None:
    """Older semantic-only carriers cannot claim exact curve readback."""
    if any("record_fps" not in states[target["id"]] or states[target["id"]].get("curve_kind") not in {"explicit_points", "identity"} for target in targets):
        return None
    return [exact_curve(target, states[target["id"]]) for target in targets]
