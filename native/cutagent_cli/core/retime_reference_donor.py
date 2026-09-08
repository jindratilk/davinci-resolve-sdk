"""Guarded native-imported reference maps for disposable timeline copies.

The owning reference workflow establishes clone provenance and runs the normal
DB session lifecycle plus native render verification. No candidate time-map
encoder is used here.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from ..errors import ValidationError
from . import clip_speed_db, retime_render_proof


def prepare_reference_donor(
    target_row: dict[str, Any], donor_row: dict[str, Any], *,
    record_fps: float, expected_source_frames: Sequence[float],
    protected_item_ids: set[str],
) -> dict[str, Any]:
    """Validate native donor coordinates against an independently supplied oracle."""
    target_id = str(target_row.get("Sm2TiItem_id") or "")
    donor_id = str(donor_row.get("Sm2TiItem_id") or "")
    if not target_id or not donor_id or target_id == donor_id or target_id in protected_item_ids:
        raise ValidationError("Reference-map target must be an independently identified disposable copy.")
    rate = float(record_fps)
    if not math.isfinite(rate) or rate <= 0:
        raise ValidationError("Reference-map timeline rate must be finite and positive.")
    duration = int(target_row.get("Duration") or 0)
    expected = tuple(float(value) for value in expected_source_frames)
    if duration <= 0 or len(expected) != duration or not all(math.isfinite(value) and value >= 0 for value in expected):
        raise ValidationError("Reference-map oracle must cover every visible output frame.")
    donor_fps = clip_speed_db._source_fps(donor_row, fallback_fps=math.nan)
    target_fps = clip_speed_db._source_fps(target_row, fallback_fps=math.nan)
    donor_in = clip_speed_db._record_in_frames(donor_row)
    target_in = clip_speed_db._record_in_frames(target_row)
    # Native NTSC trims retain a binary64 residual that interchange import can
    # round by one ULP. Keep actual subframe differences outside this allowance;
    # the transplanted map must also match the oracle at every output frame.
    trim_tolerance = max(math.ulp(donor_in), math.ulp(target_in))
    if (
        int(donor_row.get("Duration") or 0) != duration
        or abs(donor_in - target_in) > trim_tolerance
        or not math.isfinite(donor_fps) or not math.isfinite(target_fps)
        or donor_fps != target_fps
    ):
        raise ValidationError("Reference-map donor has different trim, duration, or source-rate axes.")
    blob = donor_row.get("MediaTimemapBA")
    if not isinstance(blob, bytes) or not blob:
        raise ValidationError("Reference-map donor has no native time-map payload.")
    start = int(target_row["Start"])
    transplanted = {**target_row, "MediaTimemapBA": blob}
    state = clip_speed_db.normalized_time_map_state(
        transplanted, fps=rate, record_start_frame=start, fallback_duration_frames=duration,
    )
    for offset, source in enumerate(expected):
        actual = retime_render_proof._source_at(state, start + offset)
        if not math.isfinite(actual) or abs(actual - source) > 1e-7:
            raise ValidationError(
                "Native reference map does not preserve the requested source coordinates.",
                details={"record_frame": start + offset, "expected_source_frame": source, "actual_source_frame": actual},
            )
    return {"item_id": target_id, "before_row": dict(target_row), "native_timemap": blob,
            "record_fps": rate, "expected_source_frames": expected,
            "protected_item_ids": frozenset(protected_item_ids)}


def apply_reference_donors(cursor: Any, plans: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Replace only disposable targets' map column inside an owning DB transaction."""
    if not cursor.connection.in_transaction:
        raise ValidationError("Reference-map writes require the owning DB mutation transaction.")
    ids = [plan["item_id"] for plan in plans]
    protected = set().union(*(plan["protected_item_ids"] for plan in plans))
    if not ids or len(ids) != len(set(ids)) or protected.intersection(ids):
        raise ValidationError("Reference-map targets must be distinct and outside protected originals.")
    # Validate every target before the first write. The transaction prevents a
    # concurrent writer from changing these snapshots between check and update.
    for plan in plans:
        cursor.execute("SELECT * FROM Sm2TiItem WHERE Sm2TiItem_id = ?", (plan["item_id"],))
        row = cursor.fetchone()
        if row is None or dict(row) != plan["before_row"]:
            raise ValidationError("Disposable reference target changed after planning.")
    for plan in plans:
        cursor.execute("UPDATE Sm2TiItem SET MediaTimemapBA = ? WHERE Sm2TiItem_id = ?",
                       (plan["native_timemap"], plan["item_id"]))
        if cursor.rowcount != 1:
            raise ValidationError("Reference-map write did not affect exactly one disposable target.")
    return {"changed": True, "reference_item_ids": ids, "render_verification_required": True}
