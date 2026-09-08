"""Bounded semantic rendered evidence for DB-backed retime mutations."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import math
from pathlib import Path
import shutil
import tempfile
from typing import Any

from ..errors import APICallFailed
from . import clip_ops, timeline_ops
from .effect_render_proof import compare_frames
from .retime_curve_math import bezier_roots, bezier_value
from .retime_playhead_diagnostics import move_playhead


def _source_at(state: dict[str, Any], record_frame: int) -> float:
    points = sorted(state.get("points") or [], key=lambda point: float(point.get("record_position", point["record_frame"])))
    if not points:
        raise APICallFailed("Retime proof received an empty decoded time map.")
    if record_frame <= float(points[0].get("record_position", points[0]["record_frame"])):
        return float(points[0]["source_frame"])
    for left, right in zip(points, points[1:]):
        lx = float(left.get("record_position", left["record_frame"]))
        rx = float(right.get("record_position", right["record_frame"]))
        if record_frame <= rx:
            if record_frame == rx:
                return float(right["source_frame"])
            if left.get("interpolation") == "hold" or abs(rx - lx) < 1e-9:
                return float(left["source_frame"])
            has_handles = any(
                abs(float(value) - anchor) > 1e-9
                for value, anchor in (
                    (left.get("record_frame_out", lx), lx),
                    (left.get("source_frame_out", left["source_frame"]), float(left["source_frame"])),
                    (right.get("record_frame_in", rx), rx),
                    (right.get("source_frame_in", right["source_frame"]), float(right["source_frame"])),
                )
            )
            if has_handles:
                x0, x1, x2, x3 = lx, float(left.get("record_frame_out", lx)), float(right.get("record_frame_in", rx)), rx
                y0, y1 = float(left["source_frame"]), float(left.get("source_frame_out", left["source_frame"]))
                y2, y3 = float(right.get("source_frame_in", right["source_frame"])), float(right["source_frame"])
                low, high = 0.0, 1.0
                for _ in range(40):
                    t = (low + high) / 2.0
                    mt = 1.0 - t
                    x = (mt**3 * x0) + (3 * mt * mt * t * x1) + (3 * mt * t * t * x2) + (t**3 * x3)
                    if x < record_frame:
                        low = t
                    else:
                        high = t
                t = (low + high) / 2.0
                mt = 1.0 - t
                return (mt**3 * y0) + (3 * mt * mt * t * y1) + (3 * mt * t * t * y2) + (t**3 * y3)
            ratio = (float(record_frame) - lx) / (rx - lx)
            return float(left["source_frame"]) + ratio * (float(right["source_frame"]) - float(left["source_frame"]))
    return float(points[-1]["source_frame"])


def _record_for_source(
    state: dict[str, Any], source_frame: float, *, record_start: int | None = None,
    record_end_exclusive: int | None = None,
) -> int:
    points = sorted(state.get("points") or [], key=lambda p: float(p.get("record_position", p["record_frame"])))
    if not points or not math.isfinite(source_frame):
        raise APICallFailed("Retime reference mapping requires finite source coordinates and stored points.")
    start = record_start if record_start is not None else math.ceil(points[0].get("record_position", points[0]["record_frame"]))
    end = record_end_exclusive if record_end_exclusive is not None else math.floor(points[-1].get("record_position", points[-1]["record_frame"])) + 1
    candidates: set[int] = set()

    def candidate(x: float) -> None:
        if not math.isfinite(x) or not start - 1e-7 <= x <= end - 1 + 1e-7:
            return
        for frame in (math.floor(x), math.ceil(x)):
            if start <= frame < end:
                candidates.add(frame)

    for frame in (start, end - 1):
        if start <= frame < end and abs(_source_at(state, frame) - source_frame) <= 1e-7:
            candidate(frame)
    for left, right in zip(points, points[1:]):
        lx, rx = (float(p.get("record_position", p["record_frame"])) for p in (left, right))
        ly, ry = float(left["source_frame"]), float(right["source_frame"])
        if rx < start or lx > end - 1 or rx <= lx:
            continue
        if left.get("interpolation") == "hold":
            if abs(ly - source_frame) <= 1e-7:
                candidate(max(start, math.ceil(lx)))
            continue
        x_controls = (lx, float(left.get("record_frame_out", lx)), float(right.get("record_frame_in", rx)), rx)
        y_controls = (ly, float(left.get("source_frame_out", ly)), float(right.get("source_frame_in", ry)), ry)
        for t in bezier_roots(y_controls, source_frame):
            candidate(bezier_value(x_controls, t))
        if all(abs(y - source_frame) <= 1e-7 for y in y_controls):
            candidate(max(start, math.ceil(lx)))
    # A continuous crossing between record frames is not a renderable reference.
    # Do not assume nearest/floor source quantization: frame blending and optical
    # flow can render different pixels for fractional source positions.
    candidates = {frame for frame in candidates if abs(_source_at(state, frame) - source_frame) <= 1e-7}
    if not candidates:
        raise APICallFailed(
            "The current clip cannot provide the requested source frame for retime verification.",
            details={"reason": "retime_source_reference_unavailable", "source_frame": source_frame,
                     "record_start": start, "record_end_exclusive": end}, recoverability="not_applicable",
        )
    return min(candidates, key=lambda frame: (abs(_source_at(state, frame) - source_frame), frame))


def _sample_after_frames(update: dict[str, Any]) -> list[int]:
    start = int(update["start"])
    duration = max(1, int(update["new_duration"]))
    end = start + duration - 1
    frames = {start, start + max(0, (duration - 1) // 2), start + duration - 1}
    points = sorted(update["after_state"].get("points") or [], key=lambda point: float(point.get("record_position", point["record_frame"])))
    for left, right in zip(points, points[1:]):
        left_position = float(left.get("record_position", left["record_frame"]))
        right_position = float(right.get("record_position", right["record_frame"]))
        if right_position < start or left_position > end:
            continue
        first_interior = max(start, math.floor(left_position) + 1)
        last_interior = min(end, math.ceil(right_position) - 1)
        if first_interior <= last_interior:
            frames.add((first_interior + last_interior) // 2)
        else:
            # Subframe anchors still need exact persisted readback, but there
            # is no output image between them. Check the next observable frame
            # instead of rejecting valid geometry or inventing a subframe still.
            frames.add(min(end, max(start, math.ceil((left_position + right_position) / 2))))
    # One sample per segment plus three global anchors stays within the public
    # 8196-sample limit for two curves of at most 4096 points each.
    return sorted(frames)


@contextmanager
def _still_export_page(conn: Any):
    """Native still export needs a viewer page; Deliver and Fairlight fail in v21."""
    native = getattr(conn, "resolve", None)
    get_page = getattr(native, "GetCurrentPage", None)
    original = get_page() if callable(get_page) else None
    if original not in {"deliver", "fairlight"}:
        yield
        return
    try:
        if native.OpenPage("edit") is not True or get_page() != "edit":
            raise APICallFailed(
                "DaVinci Resolve could not open the Edit page for retime frame export.",
                recoverability="manual",
            )
        yield
    finally:
        if native.OpenPage(original) is not True or get_page() != original:
            raise APICallFailed(
                "Retime rendered verification could not restore the original page.",
                details={"expected_page": original}, recoverability="manual",
            )


def _export(conn: Any, directory: Path, label: str, frame: int) -> dict[str, Any]:
    with _still_export_page(conn):
        return _export_on_viewer_page(conn, directory, label, frame)


def _export_on_viewer_page(conn: Any, directory: Path, label: str, frame: int) -> dict[str, Any]:
    try:
        timeline_start_frame = int(conn.timeline.GetStartFrame())
    except Exception:
        timeline_start_frame = int(getattr(conn, "start_frame", 0) or 0)
    positioned = move_playhead(
        timeline_ops.set_playhead, conn, f"{int(frame) - timeline_start_frame}f",
    )
    if int(positioned.get("final_frame")) != int(positioned.get("target_frame")):
        raise APICallFailed(
            "Retime rendered verification could not settle on the exact sample frame.",
            details={"sample_frame": frame, "positioned": positioned}, recoverability="manual",
        )
    path = directory / f"{label}-{frame}.png"
    exported = clip_ops.export_current_frame_as_still(conn, str(path))
    if exported.get("exported") is not True or not path.is_file() or path.stat().st_size <= 0:
        raise APICallFailed(
            "DaVinci Resolve did not render the exact retime proof frame.",
            details={"sample_frame": frame}, recoverability="manual",
        )
    return {"path": path, "record_frame": frame, "sha256": f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}", "byte_count": path.stat().st_size}


def capture_retime_reference_frames(conn: Any, updates: list[dict[str, Any]]) -> dict[str, Any]:
    """Capture pre-mutation frames selected by the intended decoded source mapping."""
    reference = None
    get_page = getattr(getattr(conn, "resolve", None), "GetCurrentPage", None)
    original_page = get_page() if callable(get_page) else None
    original_playhead = timeline_ops.get_playhead(conn)
    try:
        with _still_export_page(conn):
            reference = _capture_retime_reference_frames(conn, updates)
        return reference
    except Exception as failure:
        cleanup_retime_reference_frames(reference)
        # This wrapper runs before the DB mutation. Known missing-reference
        # and native playhead-move failures can be mutation-free only after
        # both inner restoration scopes have exited and native readback agrees.
        # Restoration errors replace the original exception and stay possible.
        if (
            isinstance(failure, APICallFailed)
            and (failure.details.get("reason") == "retime_source_reference_unavailable"
                 or failure.details.get("api_call") == "Timeline.SetCurrentTimecode")
            and isinstance(original_page, str) and original_page
            and isinstance(original_playhead, dict) and original_playhead.get("timecode")
        ):
            try:
                restored_playhead = timeline_ops.get_playhead(conn)
                if (
                    get_page() == original_page
                    and isinstance(restored_playhead, dict)
                    and restored_playhead.get("timecode") == original_playhead["timecode"]
                ):
                    failure.possible_mutation = "none"
            except Exception:
                pass  # Unknown restoration state must retain possible mutation.
        raise


def _capture_retime_reference_frames(conn: Any, updates: list[dict[str, Any]]) -> dict[str, Any]:

    video = [row for row in updates if row.get("media_kind") == "video"]
    if not video:
        raise APICallFailed("Retime verification requires at least one video target.")
    directory = Path(tempfile.mkdtemp(prefix="cutagent-retime-proof-"))
    original = timeline_ops.get_playhead(conn)
    samples: list[dict[str, Any]] = []
    try:
        for update_index, update in enumerate(video[:2]):
            after = update["after_state"]
            after_frames = _sample_after_frames(update)
            for sample_index, after_frame in enumerate(after_frames):
                source_frame = _source_at(after, after_frame)
                before_frame = _record_for_source(
                    update["before_state"], source_frame, record_start=int(update["start"]),
                    record_end_exclusive=int(update["start"]) + int(update["old_duration"]),
                )
                captured = _export(conn, directory, f"before-{update_index}-{sample_index}", before_frame)
                samples.append({"item_id": str(update["item_id"]), "before_record_frame": before_frame, "after_record_frame": after_frame, "expected_source_frame": source_frame, "before": captured, "frozen": bool(after.get("frozen")), "reversed": bool(after.get("reversed"))})
        return {"directory": directory, "original_playhead": original, "samples": samples}
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    finally:
        timecode = original.get("timecode") if isinstance(original, dict) else None
        if timecode:
            move_playhead(timeline_ops.set_playhead, conn, str(timecode), restoring=True)


def cleanup_retime_reference_frames(reference: dict[str, Any] | None) -> None:
    if isinstance(reference, dict) and isinstance(reference.get("directory"), Path):
        shutil.rmtree(reference["directory"], ignore_errors=True)


def verify_retime_renderability(conn: Any, updates: list[dict[str, Any]], *, reference: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare post-reopen pixels with pre-mutation frames chosen by the decoded map."""
    with _still_export_page(conn):
        return _verify_retime_renderability(conn, updates, reference=reference)


def _verify_retime_renderability(conn: Any, updates: list[dict[str, Any]], *, reference: dict[str, Any] | None = None) -> dict[str, Any]:

    if not reference or not reference.get("samples"):
        video = [row for row in updates if row.get("media_kind") == "video"]
        if not video:
            raise APICallFailed("Retime verification requires at least one rendered video target after project reopen.")
        directory = Path(tempfile.mkdtemp(prefix="cutagent-retime-post-proof-"))
        original = timeline_ops.get_playhead(conn)
        samples = []
        try:
            for index, update in enumerate(video[:2]):
                frame = int(update["start"]) + max(0, (max(1, int(update["new_duration"])) - 1) // 2)
                captured = _export(conn, directory, f"post-{index}", frame)
                samples.append({key: value for key, value in captured.items() if key != "path"})
            return {"status": "verified", "modality": "rendered_frame", "samples": samples, "temporary_artifacts_deleted": True, "source_files_unchanged": True}
        finally:
            timecode = original.get("timecode") if isinstance(original, dict) else None
            if timecode:
                move_playhead(timeline_ops.set_playhead, conn, str(timecode), restoring=True)
            shutil.rmtree(directory, ignore_errors=True)
    directory = reference["directory"]
    original = timeline_ops.get_playhead(conn)
    public_samples: list[dict[str, Any]] = []
    post_by_item: dict[str, list[dict[str, Any]]] = {}
    restore_error: str | None = None
    try:
        for index, sample in enumerate(reference["samples"]):
            after = _export(conn, directory, f"after-{index}", int(sample["after_record_frame"]))
            comparison = compare_frames(Path(sample["before"]["path"]), Path(after["path"]))
            proof = {
                "item_id": sample["item_id"], "before_record_frame": sample["before_record_frame"],
                "record_frame": sample["after_record_frame"], "expected_source_frame": sample["expected_source_frame"],
                "mapping": "held_source_frame" if sample["frozen"] else ("reverse_source_order" if sample["reversed"] else "decoded_source_mapping"),
                "sha256": after["sha256"], "reference_sha256": sample["before"]["sha256"],
                "decoded_pixel_match": comparison["changed"] is False, "comparison": comparison,
            }
            public_samples.append(proof)
            post_by_item.setdefault(sample["item_id"], []).append({**proof, "path": after["path"]})
        freeze_checks: list[dict[str, Any]] = []
        for item_id, samples in post_by_item.items():
            frozen = [sample for sample in reference["samples"] if sample["item_id"] == item_id and sample["frozen"]]
            if len(frozen) >= 2 and len(samples) >= 2:
                comparison = compare_frames(Path(samples[0]["path"]), Path(samples[-1]["path"]))
                freeze_checks.append({"item_id": item_id, "held_pixels_match": comparison["changed"] is False, "comparison": comparison})
        if not all(sample["decoded_pixel_match"] for sample in public_samples) or not all(check["held_pixels_match"] for check in freeze_checks):
            raise APICallFailed(
                "Rendered retime output did not match the decoded source-frame mapping.",
                details={"reason": "retime_render_mapping_mismatch", "samples": public_samples, "freeze_checks": freeze_checks}, recoverability="manual",
            )
        return {"status": "verified", "modality": "rendered_frame_mapping", "samples": public_samples, "freeze_hold_checks": freeze_checks, "temporary_artifacts_deleted": True, "source_files_unchanged": True}
    finally:
        timecode = original.get("timecode") if isinstance(original, dict) else None
        if timecode:
            try:
                move_playhead(timeline_ops.set_playhead, conn, str(timecode), restoring=True)
            except Exception as exc:
                restore_error = str(exc)
        cleanup_retime_reference_frames(reference)
        if restore_error is not None:
            raise APICallFailed(
                "Retime rendered verification could not restore the original playhead.",
                details={"restore_error": restore_error, "samples": public_samples}, recoverability="manual",
            )
