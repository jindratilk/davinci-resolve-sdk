"""Edit commands — blade, insert, overwrite, remove, trim, transitions, and FX."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional
import json as json_mod
import os
import tempfile
import zlib

import typer

from ..connection import get_connection
from ..errors import APICallFailed, handle_errors, ValidationError
from ..output import (
    output,
    is_dry_run,
    dry_run_message,
    set_execution_engine,
    set_capability_context,
    set_verification_status,
)
from ..policy import enforce_mutation_policy
from ..utils.time_ref import parse_record_frame
from ..utils.timecode import parse_time_input, seconds_to_frames, seconds_to_timecode
from ..core import (
    batch_utils,
    blade_db,
    db_session,
    db_timeline_selection,
    edit_trim_db,
    clip_ops,
    fx_template_ops,
    mutation_target,
    media_pool,
    multicam_ops,
    timeline_ops,
    transition_db,
)

app = typer.Typer(help="Edit operations — cuts, inserts, trims, transitions, and FX.")

transition_app = typer.Typer(help="Transition operations.")
app.add_typer(transition_app, name="transition")

fx_app = typer.Typer(help="ResolveFX/OFX workaround operations.")
app.add_typer(fx_app, name="fx")


def _transition_item_summary(item: Any) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, attr in (
        ("item_id", "GetUniqueId"), ("name", "GetName"),
        ("start", "GetStart"), ("end", "GetEnd"), ("duration", "GetDuration"),
    ):
        getter = getattr(item, attr, None)
        if not callable(getter):
            continue
        try:
            value = getter()
            if key in {"start", "end", "duration"}:
                value = int(value)
            elif key == "item_id":
                value = str(value or "").strip()
                if not value:
                    continue
            row[key] = value
        except Exception:
            pass
    return row


def _verify_transition_readback(conn: Any, mutation_result: Any, _session: Any) -> dict[str, Any]:
    inserted = list((mutation_result or {}).get("inserted") or []) if isinstance(mutation_result, dict) else []
    skipped_existing = list((mutation_result or {}).get("skipped_existing") or []) if isinstance(mutation_result, dict) else []
    if not inserted and skipped_existing:
        return {
            "status": "verified",
            "inserted_count": 0,
            "skipped_existing_count": len(skipped_existing),
            "checks": [],
        }
    checks: list[dict[str, Any]] = []
    items_by_track: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in inserted:
        track_type = str(row.get("track_type") or "video").lower()
        track_index = int(row.get("track_index") or 1)
        expected_start = int(row.get("start") or 0)
        expected_duration = int(row.get("duration") or 0)
        expected_name = str(row.get("pretty_type") or "").lower()
        expected_item_id = str(row.get("item_id") or "").strip()
        track_key = (track_type, track_index)
        try:
            if track_key not in items_by_track:
                items_by_track[track_key] = [
                    _transition_item_summary(item)
                    for item in (conn.timeline.GetItemListInTrack(track_type, track_index) or [])
                ]
            items = items_by_track[track_key]
        except Exception as exc:
            checks.append(
                {
                    "ok": False,
                    "track_type": track_type,
                    "track_index": track_index,
                    "expected": row,
                    "error": str(exc),
                }
            )
            continue

        matches = []
        for summary in items:
            if not expected_item_id or summary.get("item_id") != expected_item_id:
                continue
            if int(summary.get("start", -1)) != expected_start:
                continue
            if expected_duration and int(summary.get("duration", -1)) != expected_duration:
                continue
            if expected_name and expected_name not in str(summary.get("name") or "").lower():
                continue
            matches.append(summary)
        checks.append(
            {
                "ok": len(matches) == 1,
                "track_type": track_type,
                "track_index": track_index,
                "expected_item_id": expected_item_id or None,
                "observed_item_id": matches[0].get("item_id") if len(matches) == 1 else None,
                "expected": row,
                "matches": matches,
            }
        )

    return {
        "status": "verified" if inserted and all(check["ok"] for check in checks) else "failed",
        "inserted_count": len(inserted),
        "checks": checks,
    }


@transition_app.command("add")
@handle_errors
def transition_add(
    transition_type: str = typer.Argument(..., help="Transition type (default, cross-dissolve, etc.)"),
    duration: Optional[str] = typer.Argument(None, help="Transition duration (default: 24f, e.g. 12f, 0.5s, 00:00:00:12)"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain position where transition is applied"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Target clip name for deterministic selection"),
    placement: str = typer.Option("both", "--placement", help="Placement: start|end|both"),
    scope: str = typer.Option("auto", "--scope", help="Transition scope: auto|linked|video|audio"),
):
    """Add an archive-backed transition through the Disk DB route."""
    enforce_mutation_policy(
        "edit.transitions_native",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_duration = duration.strip() if isinstance(duration, str) and duration.strip() else "24f"
        dry_run_message(
            f"Would add transition type='{transition_type}' duration='{dry_run_duration}' placement='{placement}' "
            f"scope='{scope}' clip='{clip_name or 'current'}' at='{at or 'current item'}' via Disk DB"
        )
        return

    conn = get_connection(require_timeline=True)
    normalized_transition = transition_db.normalize_transition_name(transition_type)
    selection_scope = transition_db.resolve_transition_selection_scope(normalized_transition, scope)
    sdk_track_type = selection_scope if selection_scope in {"video", "audio"} else "video"
    sdk_track_index = db_timeline_selection.sdk_guard_track_index(sdk_track_type)
    sdk_track_selector = {"track": sdk_track_index} if sdk_track_index is not None else {}
    if selection_scope == "audio":
        audio_selection = db_timeline_selection.resolve_audio_group(conn, clip_name=clip_name, at=at, **sdk_track_selector)
        selected = {"video": None, "audio": audio_selection["audio"]}
    elif selection_scope == "video":
        video_selection = db_timeline_selection.resolve_video_group(conn, clip_name=clip_name, at=at, **sdk_track_selector)
        selected = {"video": video_selection["video"], "audio": None}
    else:
        selected = db_timeline_selection.resolve_linked_av_group(conn, clip_name=clip_name, at=at, **sdk_track_selector)
    selected = db_timeline_selection.require_exact_sdk_transition_selection(
        conn,
        selected=selected,
    )
    timeline_name = conn.timeline.GetName() if getattr(conn, "timeline", None) else None
    duration_ref = duration.strip() if isinstance(duration, str) and duration.strip() else None
    if duration_ref is None:
        duration_frames = transition_db.default_transition_duration_frames_for_targets(
            video_item=selected["video"],
            audio_item=selected["audio"],
        )
    else:
        duration_frames = seconds_to_frames(parse_time_input(duration_ref, conn.fps), conn.fps)
        if duration_frames <= 0:
            raise ValidationError("Transition duration must be greater than 0.", details={"duration": duration_ref})
    at_frame = parse_record_frame(str(at), conn.fps, conn.start_frame) if at else None

    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed transition add",
        writer=lambda connection, cursor, session: transition_db.add_transition_rows(
            cursor,
            video_item=selected["video"],
            audio_item=selected["audio"],
            transition_name=normalized_transition,
            duration_frames=duration_frames,
            placement=placement,
            scope=scope,
            timeline_name=timeline_name,
            at_frame=at_frame,
        ),
        verifier=_verify_transition_readback,
        pre_close_validator=lambda connection, session: db_timeline_selection.require_exact_sdk_transition_selection(
            connection,
            selected=selected,
        ),
        allow_project_name_inference=True,
        require_verified=bool(os.getenv("CUTAGENT_CLI_SDK_TRANSITION_TARGETS")),
    )
    output(data, title="Transition Add")


@transition_app.command("batch")
@handle_errors
def transition_batch(
    transition_type: Optional[str] = typer.Argument(None, help="Default transition type, e.g. cross-dissolve"),
    batch: Optional[Path] = typer.Option(None, "--batch", help="JSON batch file"),
    input_file: Optional[Path] = typer.Option(None, "--input", help="JSON batch file alias"),
    batch_json: Optional[str] = typer.Option(None, "--batch-json", help="Inline JSON batch payload"),
    select_name_regex: Optional[str] = typer.Option(None, "--select-name-regex", help="Build a batch from matching timeline item names"),
    duration_formula: Optional[str] = typer.Option(None, "--duration-formula", help="Formula: quarter-clamped"),
    duration_frames: Optional[int] = typer.Option(None, "--duration-frames", help="Fixed transition duration in frames for selector mode (default: 24)"),
    placement: str = typer.Option("both", "--placement", help="Placement: start|end|both"),
    scope: str = typer.Option("video", "--scope", help="Transition scope: auto|linked|video|audio"),
    track_type: str = typer.Option("video", "--track-type", help="Selector track type: video or audio"),
    track_index: Optional[int] = typer.Option(None, "--track", "--track-index", help="Optional selector track index"),
    allow_partial: bool = typer.Option(False, "--allow-partial", help="Apply valid entries even when some entries fail preflight"),
):
    """Batch-add DB-backed transitions with all-target preflight and idempotent skips."""
    enforce_mutation_policy(
        "edit.transitions_native",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    default_transition = transition_db.normalize_transition_name(transition_type or "cross-dissolve")
    conn = get_connection(require_timeline=True)

    if select_name_regex:
        if any(value is not None for value in (batch, input_file, batch_json)):
            raise ValidationError("--select-name-regex cannot be combined with --batch, --input, or --batch-json.")
        plans = transition_db.plan_transition_batch_by_regex(
            conn,
            name_regex=select_name_regex,
            transition_name=default_transition,
            duration_formula=duration_formula,
            duration_frames=duration_frames,
            track_type=track_type,
            track_index=track_index,
            placement=placement,
            scope=scope,
        )
        preflight_results = [
            {
                "index": int(plan.get("index", index)),
                "ok": True,
                "skipped": bool(plan.get("skipped")),
                "preflight": plan.get("preflight", plan),
            }
            for index, plan in enumerate(plans)
        ]
    else:
        entries = batch_utils.load_batch_entries(batch_path=batch, input_path=input_file, batch_json=batch_json)
        if duration_formula is not None or duration_frames is not None:
            for entry in entries:
                if duration_formula is not None and "duration_formula" not in entry and "duration_frames" not in entry and "duration" not in entry:
                    entry["duration_formula"] = duration_formula
                if duration_frames is not None and "duration_formula" not in entry and "duration_frames" not in entry and "duration" not in entry:
                    entry["duration_frames"] = duration_frames

    def _planner(entry: dict[str, Any]) -> dict[str, Any]:
        return transition_db.plan_transition_batch(
            conn,
            [entry],
            transition_name=default_transition,
            placement=placement,
            scope=scope,
        )[0]

    if not select_name_regex:
        plans, preflight_results = batch_utils.preflight_entries(entries, _planner, allow_partial=allow_partial)
    timeline_name = conn.timeline.GetName() if getattr(conn, "timeline", None) else None
    preflight = {
        "status": "passed" if all(row.get("ok") for row in preflight_results) else "partial",
        "timeline": timeline_name,
        "requested_count": len(preflight_results),
        "planned_count": len(plans),
    }

    if is_dry_run():
        output(
            batch_utils.batch_payload(
                action="edit.transition.batch",
                target={"kind": "timeline", "name": timeline_name},
                changed=False,
                dry_run=True,
                allow_partial=allow_partial,
                preflight=preflight,
                results=[
                    {**row, "changed": False}
                    for row in preflight_results
                ],
            ),
            title="Transition Batch",
        )
        return

    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed transition batch",
        writer=lambda _connection, cursor, _session: transition_db.write_transition_batch(
            cursor,
            plans=plans,
            timeline_name=timeline_name,
        ),
        verifier=_verify_transition_readback,
        allow_project_name_inference=True,
    )
    mutation_results = list(data.get("results") or [])
    if allow_partial:
        mutation_results.extend(row for row in preflight_results if row.get("error"))
    verification = data.get("verification") if isinstance(data.get("verification"), dict) else {}
    output(
        batch_utils.batch_payload(
            action="edit.transition.batch",
            target={"kind": "timeline", "name": timeline_name},
            changed=bool(data.get("inserted")),
            dry_run=False,
            allow_partial=allow_partial,
            preflight=preflight,
            results=mutation_results,
            verification=verification,
            inserted=data.get("inserted") or [],
            skipped_existing=data.get("skipped_existing") or [],
        ),
        title="Transition Batch",
    )


@fx_app.command("add")
@handle_errors
def fx_add(
    name: str = typer.Argument(..., help="Reviewed effect ID or alias"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Target timeline clip (current clip if omitted)"),
    item_id: Optional[str] = typer.Option(None, "--item-id", help="Exact native timeline item ID"),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Exact video track index; requires --record-frame"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain position inside the target"),
    template: Optional[str] = typer.Option(None, "--template", help="Reviewed custom .setting path with sibling manifest"),
    params: Optional[str] = typer.Option(None, "--params", help="JSON object of reviewed parameter IDs and typed values"),
    verify: bool = typer.Option(True, "--verify/--no-verify", help="Require structural and rendered verification"),
    proof_dir: Optional[str] = typer.Option(None, "--proof-dir", help="Directory for retained rendered evidence"),
):
    """Add one reviewed Fusion effect to one exact timeline item."""
    parsed_params = {}
    if params:
        try:
            parsed_params = json_mod.loads(params)
        except json_mod.JSONDecodeError as exc:
            raise ValidationError("Invalid JSON in --params.", details={"params": params, "error": str(exc)})
        if not isinstance(parsed_params, dict):
            raise ValidationError("--params must be a JSON object.")

    request = fx_template_ops.validate_effect_request(name, template_path=template, params=parsed_params)
    mutation_target.validate_timeline_item_selector(clip_name, item_id=item_id, track=track, record_frame=record_frame)
    if not verify:
        raise ValidationError("Consequential effect mutations require --verify.")
    effect_engine = "fusion_native" if request["path"] is None else "workaround_setting"
    enforce_mutation_policy(
        "edit.ofx_resolvefx_native",
        intended_engine=effect_engine,
        mutating=not is_dry_run(),
    )
    set_execution_engine(effect_engine)
    if is_dry_run():
        output(
            {
                "dry_run": True,
                "effect": {"id": request["spec"]["id"], "display_name": request["spec"]["name"]},
                "parameters": request["params"],
                "target_selector": {"name": clip_name, "timeline_item_id": item_id, "track": track, "record_frame": record_frame},
                "verification": {"required": True, "mode": "structural_and_rendered"},
            },
            title="FX Add Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    data = fx_template_ops.add_fx_via_template(
        conn,
        name,
        clip_name=clip_name,
        template_path=template,
        params=parsed_params,
        verify=verify,
        item_id=item_id,
        track=track,
        record_frame=record_frame,
        proof_dir=proof_dir,
    )
    output(data, title="FX Add")


# ---------------------------------------------------------------------------
# Blade
# ---------------------------------------------------------------------------

@app.command("blade")
@handle_errors
def blade(
    at: Optional[str] = typer.Option(None, "--at", help="Timecode/seconds/frames to blade at (default: playhead)"),
    track_type: str = typer.Option("all", "--track-type", help="Track type: all, video, audio"),
    track_index: int = typer.Option(0, "--track", help="Track index (0 = all matching tracks)"),
    batch: Optional[Path] = typer.Option(None, "--batch", help="JSON batch file"),
    input_file: Optional[Path] = typer.Option(None, "--input", help="JSON batch file alias"),
    batch_json: Optional[str] = typer.Option(None, "--batch-json", help="Inline JSON batch payload"),
    allow_partial: bool = typer.Option(False, "--allow-partial", help="Apply valid entries even when some entries fail preflight"),
    respect_locks: bool = typer.Option(True, "--respect-locks/--ignore-locks", help="Respect timeline track locks"),
):
    """Blade timeline clips at a given position (or playhead) through the Disk DB route."""
    enforce_mutation_policy(
        "edit.blade_native",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    normalized_track_type = blade_db.normalize_blade_track_type(track_type)
    normalized_track_index = blade_db.normalize_blade_track_index(track_index)
    batch_sources = [batch is not None, input_file is not None, batch_json is not None]
    if sum(batch_sources) > 1:
        raise ValidationError(
            "Provide only one blade batch input source.",
            details={
                "batch": str(batch) if batch else None,
                "input": str(input_file) if input_file else None,
                "batch_json": bool(batch_json),
            },
        )
    if any(batch_sources):
        entries = batch_utils.load_batch_entries(
            batch_path=batch,
            input_path=input_file,
            batch_json=batch_json,
            wrapper_keys=("cuts", "entries", "items", "batch"),
        )
    else:
        entries = [
            {
                "index": 0,
                "at": at,
                "track_type": normalized_track_type,
                "track": normalized_track_index,
            }
        ]
    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_marker_mutation_guard(conn)
    expected_targets_raw = os.environ.get("CUTAGENT_SDK_EXPECTED_BLADE_TARGETS")
    try:
        expected_targets_value = json_mod.loads(expected_targets_raw) if expected_targets_raw is not None else None
    except json_mod.JSONDecodeError as exc:
        raise ValidationError("The exact SDK blade target precondition is invalid JSON.") from exc
    expected_targets = (
        blade_db.require_exact_sdk_blade_targets(conn, expected_targets_value)
        if expected_targets_value is not None
        else None
    )
    timeline_name = conn.timeline.GetName() if getattr(conn, "timeline", None) else None
    pre_track_counts = blade_db._pre_track_counts(conn, ["video", "audio"])
    plans, preflight_results = blade_db.preflight_blade_entries(
        conn,
        entries,
        default_at=at,
        default_track_type=normalized_track_type,
        default_track_index=normalized_track_index,
        respect_locks=respect_locks,
        allow_partial=allow_partial,
    )
    if expected_targets is not None:
        revalidated_targets = blade_db.require_exact_sdk_blade_targets(conn, expected_targets_value)
        blade_db.require_blade_plans_match_exact_targets(conn, plans, revalidated_targets)
    if is_dry_run():
        output(
            blade_db.dry_run_payload(
                plans=plans,
                preflight_results=preflight_results,
                timeline_name=timeline_name,
                allow_partial=allow_partial,
            ),
            title="Blade",
        )
        return
    if not plans:
        output(
            blade_db.no_op_payload(
                preflight_results=preflight_results,
                timeline_name=timeline_name,
                allow_partial=allow_partial,
            ),
            title="Blade",
        )
        return

    def validate_exact_targets_at_locked_pre_close(locked_conn, _session):
        timeline_ops.require_sdk_marker_mutation_guard(locked_conn)
        locked_targets = blade_db.require_exact_sdk_blade_targets(locked_conn, expected_targets_value)
        blade_db.require_blade_plans_match_exact_targets(locked_conn, plans, locked_targets)

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed blade",
        writer=lambda _connection, cursor, _session: blade_db.write_blade_batch(
            cursor,
            plans=plans,
            preflight_results=preflight_results,
            timeline_name=timeline_name,
            allow_partial=allow_partial,
            pre_track_counts=pre_track_counts,
        ),
        verifier=blade_db.verify_blade_batch,
        pre_close_validator=(validate_exact_targets_at_locked_pre_close if expected_targets is not None else None),
        allow_project_name_inference=True,
        require_verified=True,
    )
    output(result, title="Blade")


@app.command("split")
@handle_errors
def split(
    at: Optional[str] = typer.Option(None, "--at", help="Timecode/seconds/frames to blade at (default: playhead)"),
    track_type: str = typer.Option("all", "--track-type", help="Track type: all, video, audio"),
    track_index: int = typer.Option(0, "--track", help="Track index (0 = all matching tracks)"),
    batch: Optional[Path] = typer.Option(None, "--batch", help="JSON batch file"),
    input_file: Optional[Path] = typer.Option(None, "--input", help="JSON batch file alias"),
    batch_json: Optional[str] = typer.Option(None, "--batch-json", help="Inline JSON batch payload"),
    allow_partial: bool = typer.Option(False, "--allow-partial", help="Apply valid entries even when some entries fail preflight"),
    respect_locks: bool = typer.Option(True, "--respect-locks/--ignore-locks", help="Respect timeline track locks"),
):
    """Blade timeline clips through the `edit split` compatibility command."""
    # Keep old scripts and auto-edit recipes working while `edit blade` remains the preferred command.
    return blade.__wrapped__(
        at=at,
        track_type=track_type,
        track_index=track_index,
        batch=batch,
        input_file=input_file,
        batch_json=batch_json,
        allow_partial=allow_partial,
        respect_locks=respect_locks,
    )


@app.command("ripple-delete-selected")
@handle_errors
def ripple_delete_selected(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Target clip name; defaults to the current video clip"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain frame/timecode inside the target item"),
    track_type: str = typer.Option("linked", "--track-type", help="Selection scope: linked, video, or audio"),
):
    """Ripple-delete a resolved timeline item through DaVinci Resolve's native DeleteClips API."""
    normalized_track_type = str(track_type or "linked").strip().lower()
    if normalized_track_type not in {"linked", "video", "audio"}:
        raise ValidationError(
            "--track-type must be one of: linked, video, audio.",
            details={"track_type": track_type, "allowed": ["linked", "video", "audio"]},
            recoverability="not_applicable",
        )
    set_execution_engine("api_native")
    set_capability_context("edit.ripple_roll_trim_native", "partial")
    enforce_mutation_policy(
        "edit.ripple_roll_trim_native",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_timeline=True)
    from ..core import timeline_precision_edit

    timeline_name = conn.timeline.GetName() if getattr(conn, "timeline", None) else None
    before = timeline_precision_edit.snapshot_timeline(conn)
    primary_kind = "audio" if normalized_track_type == "audio" else "video"
    sdk_track_index = db_timeline_selection.sdk_guard_track_index(primary_kind)
    sdk_track_selector = {"track": sdk_track_index} if sdk_track_index is not None else {}
    if clip_name:
        if primary_kind == "audio":
            selection = db_timeline_selection.resolve_audio_group(conn, clip_name=clip_name, at=at, **sdk_track_selector)
        else:
            selection = db_timeline_selection.resolve_video_group(conn, clip_name=clip_name, at=at, **sdk_track_selector)
        primary = timeline_precision_edit.match_ref(before, selection[primary_kind])
        if at:
            record_frame = parse_record_frame(str(at), conn.fps, before.start_frame)
            if not primary.start <= record_frame < primary.end:
                raise ValidationError(
                    "--at must be inside the uniquely selected ripple-delete item.",
                    details={"at": at, "record_frame": record_frame, "selection": primary.payload()},
                    recoverability="not_applicable",
                )
    elif at:
        record_frame = parse_record_frame(str(at), conn.fps, before.start_frame)
        primary = timeline_precision_edit.select_item_at(
            before,
            frame=record_frame,
            track_type=primary_kind,
            track_index=0,
        )
    else:
        if primary_kind == "audio":
            selection = db_timeline_selection.resolve_audio_group(conn, clip_name=None, at=None)
        else:
            selection = db_timeline_selection.resolve_video_group(conn, clip_name=None, at=None)
        primary = timeline_precision_edit.match_ref(before, selection[primary_kind])
    selected_states = (
        timeline_precision_edit.linked_group(before, primary.item_id)
        if normalized_track_type == "linked"
        else [primary]
    )
    selected_payload = [state.payload() for state in selected_states]
    if is_dry_run():
        output(
            {
                "action": "edit.ripple_delete_selected",
                "dry_run": True,
                "runtime_write_called": False,
                "route": "api_native_timeline_delete_clips_ripple",
                "native_api": "Timeline.DeleteClips([timelineItems], True)",
                "timeline": timeline_name,
                "requested": {"clip": clip_name, "at": at, "track_type": normalized_track_type},
                "selected": selected_payload,
                "residual_blockers": [
                    "native roll edit point mutation",
                    "native arbitrary range ripple delete without pre-splitting",
                    "native slip/slide setter parity",
                ],
            },
            title="Native Ripple Delete Selected Plan",
        )
        return

    try:
        result = timeline_precision_edit.delete_ripple(
            conn,
            before=before,
            target_ids=[state.item_id for state in selected_states],
        )
    except Exception:
        set_verification_status("failed")
        raise
    set_verification_status("verified")
    result.update(
        {
            "requested": {"clip": clip_name, "at": at, "track_type": normalized_track_type},
            "selected": selected_payload,
            "residual_blockers": [
                "native roll edit point mutation",
                "native arbitrary range ripple delete without pre-splitting",
                "native slip/slide setter parity",
            ],
        }
    )
    output(result, title="Native Ripple Delete Selected")


@app.command("slip-selected")
@handle_errors
def slip_selected(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Target video clip name; defaults to current clip"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain frame/timecode inside the target video clip"),
    direction: str = typer.Option("right", "--direction", help="Native Edit page nudge direction: left or right"),
    steps: int = typer.Option(1, "--steps", min=1, max=100, help="Number of one-frame native Slip nudges"),
):
    """Slip a selected video clip through DaVinci Resolve's native Edit page Slip mode."""
    normalized_direction = str(direction or "").strip().lower()
    if normalized_direction not in {"left", "right"}:
        raise ValidationError(
            "--direction must be left or right.",
            details={"direction": direction, "allowed": ["left", "right"]},
            recoverability="not_applicable",
        )
    set_execution_engine("resolve_gui")
    set_capability_context("edit.slip_slide", "partial")
    enforce_mutation_policy("edit.slip_slide", intended_engine="resolve_gui", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "action": "edit.slip_selected",
                "dry_run": True,
                "runtime_write_called": False,
                "route": "edit.slip_slide_gui",
                "engine_scope": "workflow_owned_resolve_gui",
                "native_ui": [
                    "Trim > Select All Clips Under Playhead",
                    "Trim > Select Nearest Clip To > Slip",
                    f"Trim > Nudge > One Frame {normalized_direction.capitalize()}",
                ],
                "requested": {"clip": clip_name, "at": at, "direction": normalized_direction, "steps": int(steps)},
                "verification": "TimelineItem source start/end changes while record start/end remain unchanged.",
            },
            title="Native Slip Selected Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    from ..core import edit_slip_slide_gui_route

    data = edit_slip_slide_gui_route.run_selected_slip_slide(
        conn,
        mode="slip",
        clip_name=clip_name,
        at=at,
        direction=normalized_direction,
        steps=int(steps),
    )
    output(data, title="Native Slip Selected")


@app.command("slide-selected")
@handle_errors
def slide_selected(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Target video clip name; defaults to current clip"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain frame/timecode inside the target video clip"),
    direction: str = typer.Option("right", "--direction", help="Native Edit page nudge direction: left or right"),
    steps: int = typer.Option(1, "--steps", min=1, max=100, help="Number of one-frame native Slide nudges"),
):
    """Slide a selected video clip through DaVinci Resolve's native Edit page Slide mode."""
    normalized_direction = str(direction or "").strip().lower()
    if normalized_direction not in {"left", "right"}:
        raise ValidationError(
            "--direction must be left or right.",
            details={"direction": direction, "allowed": ["left", "right"]},
            recoverability="not_applicable",
        )
    set_execution_engine("resolve_gui")
    set_capability_context("edit.slip_slide", "partial")
    enforce_mutation_policy("edit.slip_slide", intended_engine="resolve_gui", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "action": "edit.slide_selected",
                "dry_run": True,
                "runtime_write_called": False,
                "route": "edit.slip_slide_gui",
                "engine_scope": "workflow_owned_resolve_gui",
                "native_ui": [
                    "Trim > Select All Clips Under Playhead",
                    "Trim > Select Nearest Clip To > Slide",
                    f"Trim > Nudge > One Frame {normalized_direction.capitalize()}",
                ],
                "requested": {"clip": clip_name, "at": at, "direction": normalized_direction, "steps": int(steps)},
                "verification": "Target record span moves with unchanged source frames and adjacent clips reflow.",
                "precondition": "Target video clip must have immediate left and right neighbors on the same track.",
            },
            title="Native Slide Selected Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    from ..core import edit_slip_slide_gui_route

    data = edit_slip_slide_gui_route.run_selected_slip_slide(
        conn,
        mode="slide",
        clip_name=clip_name,
        at=at,
        direction=normalized_direction,
        steps=int(steps),
    )
    output(data, title="Native Slide Selected")


@app.command("delete-through-edit")
@handle_errors
def delete_through_edit(
    at: Optional[str] = typer.Option(None, "--at", help="Edit-point position (default: playhead)"),
    track_type: str = typer.Option("video", "--track-type", help="Track type: video, audio"),
    track_index: int = typer.Option(0, "--track", help="Track index (0 = search all)"),
    tolerance_frames: int = typer.Option(0, "--tolerance-frames", min=0, help="Accept an edit point within N frames"),
):
    """Delete a through edit by merging adjacent same-source clip segments."""
    set_execution_engine("db_workaround", 0.9)
    enforce_mutation_policy(
        "edit.delete_through_edit",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    track_type = _validate_edit_track_type(track_type)
    if is_dry_run():
        dry_run_message(
            f"Would delete through edit at {at or 'playhead'} on {track_type} track {track_index} "
            f"(tolerance={tolerance_frames}f)"
        )
        return
    conn = get_connection(require_timeline=True)
    from ..core import delete_through_edit_db

    if not at:
        tc = conn.timeline.GetCurrentTimecode()
        if not tc:
            raise APICallFailed("Cannot read playhead position.")
        from ..utils.timecode import timecode_to_seconds, seconds_to_frames

        absolute_frame = seconds_to_frames(timecode_to_seconds(tc, conn.fps), conn.fps)
        try:
            start_frame = int(conn.timeline.GetStartFrame())
        except Exception:
            start_frame = int(getattr(conn, "start_frame", 0) or 0)
        relative_frame = max(0, absolute_frame - start_frame)
        at = f"{relative_frame}f"

    result = delete_through_edit_db.delete_through_edit_at(
        conn,
        at,
        track_type=track_type,
        track_index=track_index,
        tolerance_frames=tolerance_frames,
    )
    output(result, title="Delete Through Edit")


# ---------------------------------------------------------------------------
# Insert
# ---------------------------------------------------------------------------

@app.command("insert")
@handle_errors
def insert(
    clip_name: str = typer.Argument(..., help="Media pool clip name"),
    at: str = typer.Option(..., "--at", "--record-frame", help="Timeline record-domain position"),
    source_in: Optional[str] = typer.Option(None, "--in", "--source-in", help="Half-open source-domain range start"),
    source_out: Optional[str] = typer.Option(None, "--out", "--source-out", help="Half-open source-domain range end (exclusive)"),
    track: int = typer.Option(1, "--track", min=1, help="One-based target video track, or audio track with --audio-only"),
    audio_only: bool = typer.Option(False, "--audio-only", help="Insert the source as audio only on --track"),
    media_id: Optional[str] = typer.Option(None, "--media-id", help="Authoritative Media Pool item identity"),
    audio_track: Optional[int] = typer.Option(None, "--audio-track", min=1, help="One-based linked-audio target track"),
    include_linked_audio: bool = typer.Option(True, "--include-linked-audio/--video-only", help="Insert and verify source audio when present"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Expected active project identity"),
    timeline_id: Optional[str] = typer.Option(None, "--timeline-id", help="Expected active timeline identity"),
    revision: Optional[str] = typer.Option(None, "--revision", help="Expected timeline revision from a prior dry run"),
):
    """Place a clip into an empty range without ripple and verify exact readback."""
    set_execution_engine("api_native", 1.0)
    enforce_mutation_policy(
        "edit.insert_overwrite",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_timeline=True)
    from ..core import edit_ops

    result = edit_ops.insert_clip_at(
        conn,
        clip_name,
        at,
        source_in,
        source_out,
        track,
        audio_only=audio_only,
        media_id=media_id,
        audio_track_index=audio_track,
        include_linked_audio=include_linked_audio,
        expected_project_id=project_id,
        expected_timeline_id=timeline_id,
        expected_revision=revision,
        dry_run=is_dry_run(),
    )
    output(result, title="Insert")


# ---------------------------------------------------------------------------
# Overwrite
# ---------------------------------------------------------------------------

@app.command("overwrite")
@handle_errors
def overwrite(
    clip_name: str = typer.Argument(..., help="Media pool clip name"),
    at: str = typer.Option(..., "--at", "--record-frame", help="Timeline record-domain position"),
    source_in: Optional[str] = typer.Option(None, "--in", "--source-in", help="Half-open source-domain range start"),
    source_out: Optional[str] = typer.Option(None, "--out", "--source-out", help="Half-open source-domain range end (exclusive)"),
    track: int = typer.Option(1, "--track", min=1, help="One-based target video track"),
    media_id: Optional[str] = typer.Option(None, "--media-id", help="Authoritative Media Pool item identity"),
    audio_track: Optional[int] = typer.Option(None, "--audio-track", min=1, help="One-based linked-audio target track"),
    include_linked_audio: bool = typer.Option(True, "--include-linked-audio/--video-only", help="Overwrite and verify source audio when present"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Expected active project identity"),
    timeline_id: Optional[str] = typer.Option(None, "--timeline-id", help="Expected active timeline identity"),
    revision: Optional[str] = typer.Option(None, "--revision", help="Expected timeline revision from a prior dry run"),
):
    """Replace an exact range with checkpoint recovery and fresh verification."""
    set_execution_engine("api_native", 1.0)
    enforce_mutation_policy(
        "edit.insert_overwrite",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_timeline=True)
    from ..core import edit_ops

    result = edit_ops.overwrite_clip_at(
        conn,
        clip_name,
        at,
        source_in,
        source_out,
        track,
        media_id=media_id,
        audio_track_index=audio_track,
        include_linked_audio=include_linked_audio,
        expected_project_id=project_id,
        expected_timeline_id=timeline_id,
        expected_revision=revision,
        dry_run=is_dry_run(),
    )
    output(result, title="Overwrite")


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------

_EDIT_TRACK_TYPES = {"video", "audio"}


def _validate_edit_track_type(track_type: str, *, option: str = "--track-type") -> str:
    normalized = str(track_type or "").strip().lower()
    if normalized not in _EDIT_TRACK_TYPES:
        raise ValidationError(
            "Track type must be one of: video, audio.",
            details={
                "option": option,
                "value": track_type,
                "supported_track_types": sorted(_EDIT_TRACK_TYPES),
            },
            recoverability="not_applicable",
        )
    return normalized


@app.command("remove")
@handle_errors
def remove(
    at: str = typer.Option(..., "--at", help="Position of clip to remove"),
    track_type: str = typer.Option("video", "--track-type", help="Track type: video, audio"),
    track_index: int = typer.Option(0, "--track"),
):
    """Remove the clip at a given position."""
    set_execution_engine("api_native")
    set_capability_context("edit.remove_remove_range", "partial")
    enforce_mutation_policy(
        "edit.remove_remove_range",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    track_type = _validate_edit_track_type(track_type)
    if is_dry_run():
        dry_run_message(f"Would remove clip at {at} on {track_type} track {track_index}")
        return
    conn = get_connection(require_timeline=True)
    from ..core import edit_ops

    try:
        result = edit_ops.remove_clip_at(conn, at, track_type, track_index)
    except Exception:
        set_verification_status("failed")
        raise
    set_verification_status("verified")
    output(result, title="Remove")


@app.command("remove-range")
@handle_errors
def remove_range(
    in_pos: str = typer.Option(..., "--in", help="Range start"),
    out_pos: str = typer.Option(..., "--out", help="Range end"),
    track_type: str = typer.Option("video", "--track-type", help="Track type: video, audio"),
    track_index: int = typer.Option(0, "--track"),
):
    """Remove all clips in a time range."""
    set_execution_engine("api_native")
    set_capability_context("edit.remove_remove_range", "partial")
    enforce_mutation_policy(
        "edit.remove_remove_range",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    track_type = _validate_edit_track_type(track_type)
    if is_dry_run():
        dry_run_message(f"Would remove clips in range {in_pos} - {out_pos} on {track_type} track {track_index}")
        return
    conn = get_connection(require_timeline=True)
    from ..core import edit_ops

    try:
        result = edit_ops.remove_range(conn, in_pos, out_pos, track_type, track_index)
    except Exception:
        set_verification_status("failed")
        raise
    set_verification_status("verified")
    output(result, title="Remove Range")


# ---------------------------------------------------------------------------
# Trim
# ---------------------------------------------------------------------------

@app.command("trim")
@handle_errors
def trim(
    clip_name: Optional[str] = typer.Argument(None, help="Video item name selector"),
    head: float = typer.Option(0.0, "--head", help="Trim from start (seconds)"),
    tail: float = typer.Option(0.0, "--tail", help="Trim from end (seconds)"),
    timeline_name: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    track_index: int = typer.Option(1, "--track", "--track-index", min=1, help="Video track index for selector"),
    start_frame: str | None = typer.Option(None, "--start-frame", help="Current video item start in record-domain frames/time"),
    current_end_frame: str | None = typer.Option(None, "--current-end-frame", help="Current video item end for stricter selection"),
    name: str | None = typer.Option(None, "--name", help="Current timeline item name for stricter selection"),
    linked_audio: str = typer.Option(
        "preserve",
        "--linked-audio",
        help="Linked-audio safety: preserve supports unlinked clips and fails closed on linked clips until linked preservation passes its release proof gate; exclude performs a video-only trim that may change link topology",
    ),
):
    """Trim one video item's head/tail without ripple and verify durable readback."""
    set_execution_engine("db_workaround")
    enforce_mutation_policy(
        "edit.trim_workaround",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if head < 0 or tail < 0:
        raise ValidationError("Trim head and tail must be non-negative.", details={"head": head, "tail": tail})
    if head == 0.0 and tail == 0.0:
        raise ValidationError("Specify --head and/or --tail.", details={"head": head, "tail": tail})
    if clip_name and name:
        raise ValidationError(
            "CLIP_NAME and --name are mutually exclusive.",
            details={"clip_name": clip_name, "name": name},
        )
    resolved_name = name or clip_name
    normalized_linked_audio = str(linked_audio or "").strip().lower()
    if normalized_linked_audio not in {"preserve", "exclude"}:
        raise ValidationError(
            "--linked-audio must be preserve or exclude.",
            details={"linked_audio": linked_audio, "allowed": ["preserve", "exclude"]},
        )
    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_marker_mutation_guard(conn)
    result = edit_trim_db.trim_video_item(
        conn,
        timeline_name=timeline_name,
        track_index=track_index,
        start_frame=start_frame,
        current_end_frame=current_end_frame,
        name=resolved_name,
        head_seconds=head,
        tail_seconds=tail,
        linked_audio_mode=normalized_linked_audio,
        dry_run=is_dry_run(),
    )
    output(result, title="Trim Plan" if is_dry_run() else "Trim")


# ---------------------------------------------------------------------------
# Auto Subtitle
# ---------------------------------------------------------------------------

@app.command("auto-subtitle")
@handle_errors
def auto_subtitle(
    language: Optional[str] = typer.Option(None, "--language", help="auto|english|german|..."),
    preset: Optional[str] = typer.Option(None, "--preset", help="default|teletext|netflix"),
    chars_per_line: Optional[int] = typer.Option(None, "--chars-per-line", min=1, max=60),
    line_break: Optional[str] = typer.Option(None, "--line-break", help="single|double"),
    gap: Optional[int] = typer.Option(None, "--gap", min=0, max=10, help="Gap between captions in frames/seconds per DaVinci Resolve setting"),
):
    """Create subtitle-track captions from timeline audio using DaVinci Resolve auto-caption."""
    enforce_mutation_policy(
        "timeline.subtitle_list_add_export",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would create subtitles from timeline audio via DaVinci Resolve auto-caption.")
        return
    conn = get_connection(require_timeline=True)
    data = media_pool.create_subtitles_from_audio(
        conn,
        language=language,
        preset=preset,
        chars_per_line=chars_per_line,
        line_break=line_break,
        gap=gap,
    )
    output(data, title="Auto Subtitle")
