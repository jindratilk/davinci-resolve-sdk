"""DaVinci Resolve 21.1 item-edge transitions, preserving the existing CLI placements."""
from __future__ import annotations

from ..errors import APICallFailed, ValidationError
from ..output import set_execution_engine, set_verification_status
from . import resolve_api_version, timeline_ops, transition_db
from .native_clip_audio import _item


def available(conn, selection, *, placement, at_frame, transition_name):
    if not resolve_api_version.at_least(conn, 21, 1):
        return False
    # An interior seam needs blade/split semantics which AddTransition cannot express.
    if placement == "both" and at_frame is not None:
        return all(at_frame in {ref.start, ref.end} for ref in selection.values() if ref is not None)
    return transition_name != "smooth-cut"


def add(conn, selection, *, transition_name, duration_frames, placement, scope, at_frame, verifier):
    entry = transition_db.TRANSITION_REGISTRY[transition_name]
    plans = []
    for kind in ("video", "audio"):
        ref = selection.get(kind)
        if ref is None:
            continue
        if entry.category == "audio_builtin" and kind != "audio":
            continue
        if kind == "audio" and entry.category != "audio_builtin" and transition_name != "cross-dissolve":
            continue
        use = transition_db.TRANSITION_REGISTRY["cross-fade-0db"] if kind == "audio" and transition_name == "cross-dissolve" else entry
        category = {"video_builtin": "simple", "audio_builtin": "audio", "fusion_transition": "fusion", "ofx": "ofx"}.get(use.category)
        if category is None:
            raise ValidationError("The selected transition has no documented native category.")
        for start, alignment in transition_db._transition_positions(ref, duration_frames=duration_frames, placement=placement, at_frame=at_frame):
            centered = alignment == 2
            edge = ("start" if at_frame == ref.start else "end") if centered else ("start" if alignment == 1 else "end")
            options = {"type": use.name, "category": category, "position": edge,
                       "alignment": "center" if centered else "right" if edge == "start" else "left", "duration": duration_frames}
            item = _item(conn, ref)
            if not callable(getattr(item, "AddTransition", None)):
                raise APICallFailed("DaVinci Resolve 21.1 requires TimelineItem.AddTransition.")
            for existing in conn.timeline.GetItemListInTrack(ref.track_type, ref.track_index) or []:
                if existing.GetType() == "transition" and int(existing.GetStart()) < start + duration_frames and start < int(existing.GetEnd()):
                    raise ValidationError("An existing transition overlaps the requested edge; inspect it before replacing it.")
            plans.append({"ref": ref, "options": options, "start": start, "pretty_type": use.pretty_type})
    if not plans:
        raise ValidationError("No exact item-edge transition targets were selected.")
    created = []
    try:
        timeline_ops.require_sdk_marker_mutation_guard(conn)
        for plan in plans:
            item = _item(conn, plan["ref"])
            transition = item.AddTransition(plan["options"])
            if transition is None:
                raise APICallFailed("TimelineItem.AddTransition rejected the transition.")
            created.append(transition)
            if transition.GetType() != "transition":
                raise APICallFailed("Native transition creation did not return a transition item.")
        inserted = [{"item_id": str(item.GetUniqueId()), "pretty_type": plan["pretty_type"],
                     "track_type": plan["ref"].track_type, "track_index": plan["ref"].track_index,
                     "start": plan["start"], "duration": duration_frames}
                    for item, plan in zip(created, plans)]
        data = {"transition": transition_name, "scope": scope, "placement": placement,
                "duration_frames": duration_frames, "inserted": inserted, "skipped_existing": []}
        for plan in plans:
            _item(conn, plan["ref"])
        verification = verifier(conn, data, None)
        if verification.get("status") != "verified":
            raise APICallFailed("Created transition did not match exact native readback.")
    except Exception as exc:
        if created:
            restored = False
            try:
                ids = {str(item.GetUniqueId()) for item in created}
                removed = conn.timeline.DeleteClips(created, False) is True
                remaining = {str(item.GetUniqueId()) for plan in plans
                             for item in conn.timeline.GetItemListInTrack(plan["ref"].track_type, plan["ref"].track_index) or []}
                restored = removed and not (ids & remaining)
            except Exception:
                pass
            raise APICallFailed("Native transition failed; inspect restoration before retrying.", details={"restoration_verified": restored}) from exc
        raise
    data["verification"] = verification
    set_execution_engine("api_native")
    set_verification_status("verified")
    return data
