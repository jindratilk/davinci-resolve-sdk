"""Canonical multicam command family."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import typer

from ..connection import get_connection
from ..core import multicam_engine, multicam_source, multicam_ui_verdicts, native_multicam_db, podcast_audio_activity, podcast_multicam, sdk_live_inspection, timeline_ops
from ..errors import ConfirmationRequired, ValidationError, handle_errors
from ..output import dry_run_message, is_dry_run, is_machine_mode, mutation_payload, output, set_execution_engine
from ..policy import enforce_mutation_policy
from ..runtime_health import resolve_current_disk_project_db

app = typer.Typer(help="Native multicam primitives and structured job execution.")
replace_app = typer.Typer(help="Replace media inside native multicam angles.")
audio_activity_app = typer.Typer(help="Diagnose and calibrate audio-activity podcast multicam switching.")
angle_app = typer.Typer(help="Edit persistent internal multicam angle tracks.")
source_app = typer.Typer(help="Edit distinct source items inside multicam angles.")
app.add_typer(replace_app, name="replace")
app.add_typer(audio_activity_app, name="audio-activity")
app.add_typer(angle_app, name="angle")
app.add_typer(source_app, name="source")


def _require_sdk_multicam_native_identity(conn, multicam_name: str) -> str | None:
    expected = os.environ.get("CUTAGENT_SDK_EXPECTED_MULTICAM_NATIVE_ID", "").strip()
    if not expected:
        return None
    root = conn.media_pool.GetRootFolder()
    matches: list[dict[str, object]] = []
    if root:
        multicam_engine.media_pool._collect_clip_object_matches(root, matches)
    exact = [
        match for match in matches
        if timeline_ops.documented_sdk_media_pool_id(match.get("clip")) == expected
    ]
    if len(exact) != 1 or str(exact[0].get("name") or "") != multicam_name:
        from ..errors import SdkMutationStaleRevision

        raise SdkMutationStaleRevision(
            "The exact SDK multicam identity changed before execution.",
            details={"multicam_name": multicam_name},
        )
    unique_id_getter = getattr(exact[0].get("clip"), "GetUniqueId", None)
    database_native_id = str(unique_id_getter() or "").strip() if callable(unique_id_getter) else ""
    if not database_native_id:
        raise ValidationError(
            "The exact SDK multicam target has no Project.db identity.",
            details={"multicam_name": multicam_name},
        )
    return database_native_id


def _require_sdk_isolated_multicam_program(conn, *, multicam_media_id: str | None, switch_scope: str) -> None:
    if not multicam_media_id:
        return
    expected_public_id = os.environ.get("CUTAGENT_SDK_EXPECTED_MULTICAM_NATIVE_ID", "").strip()
    track_types = ["video", "audio"] if switch_scope == "linked" else [switch_scope]
    timeline = conn.timeline
    for track_type in track_types:
        track_count = int(timeline.GetTrackCount(track_type) or 0)
        populated = [
            (track_index, list(timeline.GetItemListInTrack(track_type, track_index) or []))
            for track_index in range(1, track_count + 1)
        ]
        populated = [(track_index, items) for track_index, items in populated if items]
        if len(populated) != 1 or populated[0][0] != 1:
            raise ValidationError(
                "SDK multicam switching requires an isolated target program on track 1.",
                details={"reason": "sdk_multicam_program_not_isolated", "track_type": track_type},
            )
        cursor = int(getattr(conn, "start_frame", 0) or 0)
        for item in sorted(populated[0][1], key=lambda candidate: int(candidate.GetStart())):
            media_pool_item = item.GetMediaPoolItem() if hasattr(item, "GetMediaPoolItem") else None
            if timeline_ops.documented_sdk_media_pool_id(media_pool_item) != expected_public_id:
                raise ValidationError(
                    "SDK multicam switching refused non-target content on an affected track.",
                    details={"reason": "sdk_multicam_program_contains_unrelated_content", "track_type": track_type},
                )
            start = int(item.GetStart())
            end = int(item.GetEnd())
            if start != cursor or end <= start:
                raise ValidationError(
                    "SDK multicam switching requires a contiguous target program from the timeline start.",
                    details={"reason": "sdk_multicam_program_not_contiguous", "track_type": track_type},
                )
            cursor = end


def _require_sdk_timeline_native_identity(conn, timeline_name: str) -> str | None:
    expected = os.environ.get("CUTAGENT_SDK_EXPECTED_TIMELINE_NATIVE_ID", "").strip()
    if not expected:
        return None
    timeline = getattr(conn, "timeline", None)
    actual_name = str(timeline.GetName() or "").strip() if timeline and hasattr(timeline, "GetName") else ""
    actual_id = timeline_ops.documented_sdk_unique_id(timeline) if timeline is not None else None
    if actual_name != timeline_name or actual_id != expected:
        from ..errors import SdkMutationStaleRevision

        raise SdkMutationStaleRevision(
            "The exact SDK timeline identity changed before execution.",
            details={"timeline_name": timeline_name},
        )
    return expected


def _require_sdk_multicam_create_guard(conn) -> None:
    expected = os.environ.get("CUTAGENT_SDK_MULTICAM_CREATE_GUARD", "").strip()
    if not expected:
        return
    inspected = sdk_live_inspection.inspect_media_pool_page(
        conn,
        deadline_at_ms=None,
        offset=0,
        page_size=1,
        search=None,
    )
    actual = str(inspected.get("pool_digest") or "")
    if actual != expected or inspected.get("ambiguous_native_ids") is not False:
        from ..errors import SdkMutationStaleRevision

        raise SdkMutationStaleRevision(
            "The exact SDK Media Pool revision changed before multicam creation.",
            details={"reason": "sdk_multicam_create_guard_mismatch"},
        )


def _run_persistent_angle_edit(
    *,
    operation: str,
    multicam_name: str | None,
    media_id: str | None,
    sequence_id: str | None,
    angle_number: int,
    media_type: str = "both",
    item_index: int | None = None,
    record_start_frame: int | None = None,
    name: str | None = None,
    enabled: bool | None = None,
) -> dict[str, object]:
    conn = get_connection(require_project=True)
    expected_source_media_id = os.environ.get("CUTAGENT_SDK_EXPECTED_MULTICAM_SOURCE_NATIVE_ID", "").strip() or None
    expected_item_index_text = os.environ.get("CUTAGENT_SDK_EXPECTED_MULTICAM_SOURCE_ITEM_INDEX", "").strip()
    expected_item_index = int(expected_item_index_text) if expected_item_index_text else None
    if expected_item_index is not None and item_index != expected_item_index:
        from ..errors import SdkMutationStaleRevision

        raise SdkMutationStaleRevision("The exact SDK multicam source item changed before execution.")
    kwargs = {
        "operation": operation,
        "multicam_name": multicam_name,
        "media_id": media_id,
        "sequence_id": sequence_id,
        "angle_number": angle_number,
        "media_type": media_type,
        "item_index": item_index,
        "record_start_frame": record_start_frame,
        "name": name,
        "enabled": enabled,
        "expected_source_media_id": expected_source_media_id,
    }
    if is_dry_run():
        current_db = resolve_current_disk_project_db(conn)
        return native_multicam_db.plan_multicam_angle_edit(
            str(current_db["project_db_path"]),
            **kwargs,
        )
    return native_multicam_db.edit_multicam_angle(conn, **kwargs)


def _parse_resolve_angle_number(value: object, *, option_name: str) -> int:
    text = str(value or "").strip()
    match = re.fullmatch(r"(?:Angle\s*)?([1-9][0-9]*)", text, flags=re.IGNORECASE)
    if not match:
        raise ValidationError(
            "Multicam angle targets use DaVinci Resolve's one-based Angle number.",
            details={"option": option_name, "value": value, "example": "1=/absolute/path.wav"},
        )
    return int(match.group(1))


def _parse_resolve_angle_media_targets(specs: list[str] | None, *, media_kind: str) -> list[dict[str, object]]:
    targets: list[dict[str, object]] = []
    seen: set[int] = set()
    for raw in list(specs or []):
        text = str(raw or "").strip()
        if "=" not in text:
            raise ValidationError(
                "Multicam replace angle target must use ANGLE=/path syntax.",
                details={"spec": raw, "media_kind": media_kind, "example": "1=/absolute/path.mov"},
            )
        angle_text, path_text = [part.strip() for part in text.split("=", 1)]
        angle_number = _parse_resolve_angle_number(angle_text, option_name="--angle")
        if angle_number in seen:
            raise ValidationError(
                "Multicam replace angle targets must be unique.",
                details={"angle_number": angle_number, "spec": raw},
            )
        if not path_text:
            raise ValidationError(
                "Multicam replace angle target path cannot be empty.",
                details={"angle_number": angle_number, "spec": raw},
            )
        seen.add(angle_number)
        targets.append(
            {
                "angle_number": angle_number,
                "angle_index": angle_number - 1,
                "source_id": f"angle_{angle_number}",
                "path": path_text,
                "clip_name": Path(path_text).expanduser().name,
                "media_kind": media_kind,
            }
        )
    return targets


def _parse_resolve_angle_numbers(values: list[int] | list[str] | None, *, option_name: str) -> list[int]:
    numbers: list[int] = []
    seen: set[int] = set()
    for raw in list(values or []):
        angle_number = _parse_resolve_angle_number(raw, option_name=option_name)
        if angle_number in seen:
            raise ValidationError(
                "Multicam angle number targets must be unique.",
                details={"option": option_name, "angle_number": angle_number},
            )
        seen.add(angle_number)
        numbers.append(angle_number)
    return numbers


def _parse_angle_offset_specs(specs: list[str] | None) -> dict[int, int]:
    offsets: dict[int, int] = {}
    for raw in list(specs or []):
        text = str(raw or "").strip()
        if "=" not in text:
            raise ValidationError(
                "Multicam replace offset must use ANGLE=frames syntax.",
                details={"spec": raw, "example": "1=-12"},
            )
        angle_text, frames_text = [part.strip() for part in text.split("=", 1)]
        angle_number = _parse_resolve_angle_number(angle_text, option_name="--offset")
        if angle_number in offsets:
            raise ValidationError(
                "Multicam replace offset targets must be unique.",
                details={"angle_number": angle_number, "spec": raw},
            )
        try:
            offsets[angle_number] = int(frames_text)
        except ValueError as exc:
            raise ValidationError(
                "Multicam replace offset frames must be an integer.",
                details={"angle_number": angle_number, "value": frames_text},
            ) from exc
    return offsets


def _angle_number_frame_map_to_indices(values: dict[int, int]) -> dict[int, int]:
    return {int(angle_number) - 1: int(frames) for angle_number, frames in values.items()}


def _load_multicam_source_specs(
    *,
    source_specs_path: str | None,
    source_specs_json: str | None,
) -> list[dict[str, object]]:
    if bool(source_specs_path) == bool(source_specs_json):
        raise ValidationError(
            "Provide exactly one of --source-specs or --source-specs-json.",
            details={
                "source_specs": source_specs_path,
                "source_specs_json": bool(source_specs_json),
            },
            recoverability="not_applicable",
        )

    if source_specs_path:
        raw = json.loads(Path(source_specs_path).read_text(encoding="utf-8"))
    else:
        raw = json.loads(str(source_specs_json))

    if isinstance(raw, dict):
        for key in ("source_specs", "specs", "sources", "entries", "items"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break

    if not isinstance(raw, list):
        raise ValidationError(
            "Source specs input must be a JSON array or an object with source_specs/specs/sources/entries/items.",
            details={"payload_type": type(raw).__name__},
            recoverability="not_applicable",
        )

    entries: list[dict[str, object]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValidationError(
                "Each source spec must be a JSON object.",
                details={"index": index, "entry": entry},
                recoverability="not_applicable",
            )
        entries.append(dict(entry))
    return entries


def _normalize_cli_angle_sources(angle_specs: list[str] | None) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for raw_spec in list(angle_specs or []):
        for raw_entry in str(raw_spec).split(","):
            entry = raw_entry.strip()
            if not entry:
                continue
            entry_map = podcast_multicam._parse_angle_spec(entry)
            for angle, source_value in entry_map.items():
                source_text = str(source_value).strip()
                path_parts = [part for part in re.split(r"[/\\\\]+", source_text) if part]
                is_path = len(path_parts) > 1 or bool(re.match(r"^[A-Za-z]:[/\\\\]", source_text))
                source = {
                    "angle": angle,
                    "clip_name": path_parts[-1] if is_path else source_text,
                }
                if is_path:
                    source["source_path"] = source_text
                parsed.append(source)
    return parsed


def _normalize_cli_angle_map(angle_specs: list[str] | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for source in _normalize_cli_angle_sources(angle_specs):
        parsed.setdefault(source["angle"], source["clip_name"])
    return parsed


def _parse_video_source_offset_specs(specs: list[str] | None, *, angle_map: dict[str, str]) -> dict[str, int]:
    offsets: dict[str, int] = {}
    for raw in list(specs or []):
        text = str(raw or "").strip()
        if "=" not in text:
            raise ValidationError(
                "Video source offsets must use ANGLE=frames syntax.",
                details={"spec": raw, "example": "A=104"},
            )
        angle, frames_text = [part.strip() for part in text.split("=", 1)]
        if angle not in angle_map:
            raise ValidationError(
                "Video source offset references an unknown multicam angle.",
                details={"angle": angle, "known_angles": sorted(angle_map.keys()), "spec": raw},
            )
        if angle in offsets:
            raise ValidationError(
                "Video source offsets must be unique per angle.",
                details={"angle": angle, "spec": raw},
            )
        try:
            offsets[angle] = int(frames_text)
        except ValueError as exc:
            raise ValidationError(
                "Video source offset frames must be an integer.",
                details={"angle": angle, "value": frames_text},
            ) from exc
    return offsets


def _has_convenience_multicam_input(*values: object) -> bool:
    for value in values:
        if isinstance(value, typer.models.OptionInfo):
            continue
        if isinstance(value, list) and value:
            return True
        if isinstance(value, str) and value.strip():
            return True
        if value is not None and not isinstance(value, (str, list)):
            return True
    return False


def _typer_default(value: object, default: object = None) -> object:
    return default if isinstance(value, typer.models.OptionInfo) else value


def _bool_option(value: object, default: bool = False) -> bool:
    return bool(_typer_default(value, default))


def _parse_optional_seconds(value: float | None) -> int | None:
    resolved = _typer_default(value)
    if resolved is None:
        return None
    numeric = float(resolved)
    if numeric <= 0:
        raise ValidationError("Duration limits must be greater than zero.", details={"duration_limit_seconds": numeric})
    return int(round(numeric * 1000.0))


def _apply_audio_offsets_json_sync(sync_payload: dict[str, object], audio_offsets_json: str | None) -> dict[str, object]:
    loaded_payload = podcast_audio_activity.load_audio_offsets_payload(_typer_default(audio_offsets_json))
    loaded_offsets = dict(loaded_payload.get("offsets") or {}) if isinstance(loaded_payload, dict) else {}
    if not loaded_offsets:
        return sync_payload

    mode = str(sync_payload.get("mode") or "prealigned").strip()
    if mode in {"", "prealigned"}:
        sync_payload["mode"] = "offsets-json"
    elif mode not in {"offsets", "offsets-json"}:
        raise ValidationError(
            "--audio-offsets-json can only be used with --audio-sync offsets-json.",
            details={
                "audio_sync": mode,
                "audio_offsets_json": audio_offsets_json,
                "supported_modes": ["offsets-json"],
                "hint": "Omit --audio-sync or set --audio-sync offsets-json when providing an offsets JSON file.",
            },
            recoverability="not_applicable",
        )
    sync_payload["offsets"] = loaded_offsets
    if isinstance(loaded_payload.get("offsets_seconds"), dict):
        sync_payload["offsets_seconds"] = dict(loaded_payload["offsets_seconds"])
    for key in ("fps", "offset_domain", "anchor", "anchor_label", "anchor_angle"):
        if key in loaded_payload:
            sync_payload[key] = loaded_payload[key]
    return sync_payload


def _build_multicam_convenience_job(
    *,
    operation: str,
    angle_specs: list[str] | None,
    timeline_name: str | None,
    multicam_name: str | None,
    sync_mode: str | None = None,
    transcript_path: str | None = None,
    speaker_map: str | None = None,
    switch_by: str | None = None,
    audio_source_specs: list[str] | None = None,
    audio_angle_map: str | None = None,
    audio_target_specs: list[str] | None = None,
    audio_sync: str | None = None,
    sync_reference_audio: str | None = None,
    sync_reference_angle: str | None = None,
    audio_offsets_json: str | None = None,
    overlap_policy: str | None = None,
    overlap_angle: str | None = None,
    analysis_window_ms: int | None = None,
    activity_floor_db: float | None = None,
    activity_margin_db: float | None = None,
    dominance_margin_db: float | None = None,
    min_switch_ms: int | None = None,
    switch_delay_ms: int | None = None,
    max_silence_hold_ms: int | None = None,
    video_source_offset_specs: list[str] | None = None,
    allow_unresolved_targets: bool = False,
    replace_active_timeline: bool = False,
) -> dict[str, object]:
    switch_by = _typer_default(switch_by)
    transcript_path = _typer_default(transcript_path)
    speaker_map = _typer_default(speaker_map)
    audio_source_specs = _typer_default(audio_source_specs)
    audio_angle_map = _typer_default(audio_angle_map)
    audio_target_specs = _typer_default(audio_target_specs)
    audio_sync = _typer_default(audio_sync)
    sync_reference_audio = _typer_default(sync_reference_audio)
    sync_reference_angle = _typer_default(sync_reference_angle)
    audio_offsets_json = _typer_default(audio_offsets_json)
    overlap_policy = _typer_default(overlap_policy)
    overlap_angle = _typer_default(overlap_angle)
    analysis_window_ms = _typer_default(analysis_window_ms)
    activity_floor_db = _typer_default(activity_floor_db)
    activity_margin_db = _typer_default(activity_margin_db)
    dominance_margin_db = _typer_default(dominance_margin_db)
    min_switch_ms = _typer_default(min_switch_ms)
    switch_delay_ms = _typer_default(switch_delay_ms)
    max_silence_hold_ms = _typer_default(max_silence_hold_ms)
    video_source_offset_specs = _typer_default(video_source_offset_specs)
    angle_sources = _normalize_cli_angle_sources(angle_specs)
    angle_map: dict[str, str] = {}
    for source in angle_sources:
        angle_map.setdefault(source["angle"], source["clip_name"])
    if not angle_sources:
        raise ValidationError(
            "Convenience multicam mode requires at least one --angle.",
            details={"operation": operation},
        )

    resolved_timeline_name = str(timeline_name or "").strip()
    if not resolved_timeline_name:
        raise ValidationError(
            "Convenience multicam mode requires --timeline-name.",
            details={"operation": operation},
        )

    resolved_multicam_name = str(multicam_name or f"{resolved_timeline_name} Multicam").strip()
    if not resolved_multicam_name:
        raise ValidationError(
            "Convenience multicam mode requires a non-empty multicam name.",
            details={"operation": operation},
        )

    angle_order = list(angle_map.keys())
    first_angle = angle_order[0]
    job: dict[str, object] = {
        "sources": angle_sources,
        "selection_policy_result": {
            "strategy": "explicit_cli_angles",
            "source": f"multicam {operation}",
        },
        "timeline_settings": {
            "timeline_name": resolved_timeline_name,
            "replace_active_timeline": bool(replace_active_timeline),
        },
        "multicam_settings": {
            "timeline_name": resolved_timeline_name,
            "multicam_name": resolved_multicam_name,
            "sync_mode": str(sync_mode or native_multicam_db.DEFAULT_NATIVE_ANGLE_SYNC_MODE).strip()
            or native_multicam_db.DEFAULT_NATIVE_ANGLE_SYNC_MODE,
            "sync_engine": "cutagent",
            "source_layout": "contiguous",
            "source_item_representation": "distinct_timeline_items",
            "angle_order": angle_order,
            "default_video_angle": first_angle,
            "default_audio_angle": first_angle,
        },
    }

    if operation == "switch":
        video_source_offsets = _parse_video_source_offset_specs(video_source_offset_specs, angle_map=angle_map)
        if video_source_offsets:
            job["multicam_settings"] = {
                **job["multicam_settings"],
                "video_source_offsets_frames": video_source_offsets,
            }
        resolved_switch_by = str(switch_by or "transcript").strip()
        if resolved_switch_by not in {"transcript", "audio-activity"}:
            raise ValidationError(
                "Unsupported multicam switch planning mode.",
                details={"switch_by": resolved_switch_by, "supported": ["transcript", "audio-activity"]},
            )
        job["switch_by"] = resolved_switch_by
        resolved_transcript_path = str(transcript_path or "").strip()
        if resolved_switch_by == "transcript" and not resolved_transcript_path:
            raise ValidationError(
                "Convenience multicam switch requires --transcript.",
                details={"operation": operation},
            )
        if resolved_switch_by == "transcript":
            job["multicam_settings"] = {
                **job["multicam_settings"],
                "hold_short_utterances": False,
                "reaction_hold_ms": 0,
                "switch_on": ["speaker_active"],
                "switch_exceptions": [],
            }
            job["rule_program"] = {
                "kind": "speaker_transcript_v1",
                "transcript_path": resolved_transcript_path,
                "speaker_map": podcast_multicam.parse_speaker_mapping(speaker_map),
                "filler_tokens": [],
            }
        else:
            if not str(audio_sync or "").strip():
                raise ValidationError(
                    "Convenience audio-activity switch requires --audio-sync.",
                    details={"operation": operation, "switch_by": resolved_switch_by},
                )
            audio_sources = podcast_audio_activity.parse_audio_sources(audio_source_specs)
            if not audio_sources:
                raise ValidationError(
                    "Convenience audio-activity switch requires at least one --audio-source.",
                    details={"operation": operation, "switch_by": resolved_switch_by},
                )
            sync_payload: dict[str, object] = {"mode": str(audio_sync or "").strip()}
            if sync_reference_audio:
                sync_payload["reference_audio_path"] = str(sync_reference_audio).strip()
            if sync_reference_angle:
                sync_payload["reference_angle"] = str(sync_reference_angle).strip()
            if (
                str(sync_payload.get("mode") or "").strip() == "waveform"
                and not sync_payload.get("reference_audio_path")
                and not sync_payload.get("reference_angle")
            ):
                sync_payload["reference_angle"] = first_angle
            sync_payload = _apply_audio_offsets_json_sync(sync_payload, audio_offsets_json)
            overlap_payload: dict[str, object] = {}
            if overlap_policy:
                overlap_payload["policy"] = str(overlap_policy).strip()
            if overlap_angle:
                overlap_payload["angle"] = str(overlap_angle).strip()
                overlap_payload.setdefault("policy", "angle")
            switching_payload = {
                "analysis_window_ms": analysis_window_ms,
                "activity_floor_db": activity_floor_db,
                "activity_margin_db": activity_margin_db,
                "dominance_margin_db": dominance_margin_db,
                "min_switch_ms": min_switch_ms,
                "switch_delay_ms": switch_delay_ms,
                "max_silence_hold_ms": 0 if max_silence_hold_ms is None else max_silence_hold_ms,
            }
            job["rule_program"] = {
                "kind": "audio_activity_v1",
                "audio_sources": audio_sources,
                "audio_angle_map": podcast_audio_activity.parse_audio_angle_map(audio_angle_map),
                "audio_targets": podcast_audio_activity.parse_audio_targets(audio_target_specs),
                "audio_sync": sync_payload,
                "switching": switching_payload,
                "overlap": overlap_payload,
                "allow_unresolved_targets": bool(allow_unresolved_targets),
            }
        job["verification_requirements"] = {
            "require_native_multicam": True,
            "require_native_multicam_segments": True,
            "require_switch_menu": True,
        }

    return job


def _multicam_settings_job_context() -> dict[str, object]:
    example_job = {
        "sources": [
            {"angle": "A", "clip_name": "Cam A"},
            {"angle": "B", "clip_name": "Cam B"},
        ],
        "timeline_settings": {"timeline_name": "Podcast Edit"},
        "multicam_settings": {
            "multicam_name": "Podcast Edit Multicam",
            "sync_mode": native_multicam_db.DEFAULT_NATIVE_ANGLE_SYNC_MODE,
            "min_shot_ms": 1200,
            "merge_gap_ms": 250,
        },
    }
    return {
        "requires_job": True,
        "reason": "multicam settings resolves defaults from a structured multicam job and does not read DaVinci Resolve state by itself.",
        "accepted_inputs": ["--job /absolute/path/job.json", "--job-json '{...}'"],
        "required_top_level_keys": ["sources", "timeline_settings", "multicam_settings"],
        "source_schema": {
            "minimum_count": 2,
            "required_fields": ["angle", "clip_name"],
            "optional_identity_fields": ["folder", "source_path"],
            "optional_timing_fields": ["record_start_frame", "source_in_frame", "duration_frames"],
            "source_duration_field": "source_duration_frames",
            "timing_semantics": {
                "record_start_frame": "zero-based frame relative to the native multicam container start",
                "source_in_frame": "zero-based source-media frame",
                "duration_frames": "positive item duration used identically for paired video and audio items",
            },
        },
        "supported_source_layouts": ["contiguous", "sparse"],
        "default_sync_engine": "cutagent",
        "davinci_sound_sync_used": False,
        "supported_sync_modes": list(native_multicam_db.NATIVE_ANGLE_SYNC_MODES),
        "example_job": example_job,
        "example_commands": [
            "cutagent multicam settings --job /absolute/path/job.json --json",
            f"cutagent multicam settings --job-json '{json.dumps(example_job, separators=(',', ':'))}' --json",
        ],
    }


def _load_angle_order_input(
    *,
    angle_order: list[str] | None,
    angle_order_json: str | None,
) -> list[str]:
    requested = [str(value or "").strip() for value in list(angle_order or []) if str(value or "").strip()]
    json_path = Path(str(angle_order_json or "").strip()).expanduser() if str(angle_order_json or "").strip() else None
    if json_path is not None:
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValidationError(
                "Native multicam angle reorder could not read the requested angle-order JSON file.",
                details={
                    "reason": "angle_order_json_not_found",
                    "angle_order_json": str(json_path),
                },
            ) from exc
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "Native multicam angle reorder angle-order JSON file is not valid JSON.",
                details={
                    "reason": "angle_order_json_invalid",
                    "angle_order_json": str(json_path),
                    "line": exc.lineno,
                    "column": exc.colno,
                },
            ) from exc

        if isinstance(payload, dict):
            payload = payload.get("angle_order")
        if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
            raise ValidationError(
                "Native multicam angle reorder angle-order JSON must be an array of strings or an object with angle_order[].",
                details={
                    "reason": "angle_order_json_invalid_shape",
                    "angle_order_json": str(json_path),
                },
            )
        requested.extend(str(item or "").strip() for item in payload if str(item or "").strip())
    if not requested:
        raise ValidationError(
            "Native multicam angle reorder requires --angle-order and/or --angle-order-json.",
            details={"reason": "missing_angle_order"},
        )
    return requested


def _load_optional_angle_order_input(
    *,
    angle_order: list[str] | None,
    angle_order_json: str | None,
) -> list[str]:
    if not list(angle_order or []) and not str(angle_order_json or "").strip():
        return []
    return _load_angle_order_input(angle_order=angle_order, angle_order_json=angle_order_json)


class _DryRunTimelineContext:
    @staticmethod
    def GetName() -> str:
        return "Dry Run Timeline"


class _DryRunMulticamContext:
    fps = 24.0
    start_frame = 0
    timeline = _DryRunTimelineContext()


@audio_activity_app.command("calibrate")
@handle_errors
def audio_activity_calibrate(
    angle: list[str] | None = typer.Option(None, "--angle", help="Repeatable angle spec: A=camA.mov"),
    audio_source: list[str] | None = typer.Option(None, "--audio-source", help="Repeatable audio activity source spec: id=/path/audio.wav"),
    audio_angle_map: str | None = typer.Option(None, "--audio-angle-map", help="Audio activity mapping: source_id=ANGLE,source_id=ANGLE"),
    audio_target: list[str] | None = typer.Option(None, "--audio-target", help="Repeatable flexible target spec: source_id=ANGLE or source_id=ANGLE_A,ANGLE_B"),
    audio_sync: str | None = typer.Option("prealigned", "--audio-sync", help="Audio sync mode: prealigned, waveform, offsets-json"),
    sync_reference_audio: str | None = typer.Option(None, "--sync-reference-audio", help="Reference camera/audio file for waveform audio sync"),
    sync_reference_angle: str | None = typer.Option(None, "--sync-reference-angle", help="Reference angle for waveform audio sync when --angle contains source paths"),
    sync_reference_source: list[str] | None = typer.Option(None, "--sync-reference-source", help="Repeatable source-specific waveform reference: source_id=/path/reference_camera.mov"),
    audio_offsets_json: str | None = typer.Option(None, "--audio-offsets-json", help="Path to JSON offsets object for audio-activity sync"),
    overlap_policy: str | None = typer.Option(None, "--overlap-policy", help="Overlap handling while scoring: angle/wide, dominant, hold, mark"),
    overlap_angle: str | None = typer.Option(None, "--overlap-angle", "--wide-angle", help="Multicam angle to use for overlap/wide moments"),
    transcript: str | None = typer.Option(None, "--transcript", help="Optional speaker-labelled transcript JSON for transcript-assisted calibration"),
    transcript_speaker_map: str | None = typer.Option(None, "--transcript-speaker-map", help="Optional transcript speaker to audio source mapping: speaker_0=speaker_1,speaker_1=speaker_2"),
    style: str = typer.Option("balanced", "--style", help="Calibration style: balanced, reactive, calm"),
    duration_limit_seconds: float | None = typer.Option(None, "--duration-limit-seconds", help="Analyze only the first N seconds for quick calibration"),
    fps: float = typer.Option(24.0, "--fps", help="Timeline frames per second for waveform offset conversion"),
    write_analysis: str | None = typer.Option(None, "--write-analysis", help="Optional JSON path to write the full calibration result"),
    ranked_candidates: int = typer.Option(8, "--ranked-candidates", min=1, max=50, help="Number of ranked candidates to include in the response"),
):
    """Recommend audio-activity switching thresholds without mutating DaVinci Resolve."""
    set_execution_engine("api_native")
    enforce_mutation_policy("multicam.audio_activity_calibrate", intended_engine="api_native", mutating=False)
    angle_map = _normalize_cli_angle_map(_typer_default(angle))
    if not angle_map:
        raise ValidationError("Audio activity calibration requires at least one --angle.", details={"angle": angle})
    audio_sources = podcast_audio_activity.parse_audio_sources(_typer_default(audio_source))
    if not audio_sources:
        raise ValidationError("Audio activity calibration requires at least one --audio-source.", details={"audio_source": audio_source})
    sync_payload: dict[str, object] = {"mode": str(_typer_default(audio_sync, "prealigned") or "prealigned").strip()}
    if sync_reference_audio:
        sync_payload["reference_audio_path"] = str(sync_reference_audio).strip()
    if sync_reference_angle:
        sync_payload["reference_angle"] = str(sync_reference_angle).strip()
    source_references = {
        source_id: reference_path
        for source_id, reference_path in (
            podcast_audio_activity.parse_key_value_spec(raw, value_name="Sync reference source")
            for raw in list(_typer_default(sync_reference_source) or [])
        )
    }
    if source_references:
        sync_payload["source_reference_paths"] = source_references
    sync_payload = _apply_audio_offsets_json_sync(sync_payload, _typer_default(audio_offsets_json))
    overlap_payload: dict[str, object] = {}
    if overlap_policy:
        overlap_payload["policy"] = str(overlap_policy).strip()
    if overlap_angle:
        overlap_payload["angle"] = str(overlap_angle).strip()
    analysis = podcast_audio_activity.calibrate_audio_activity(
        audio_sources=audio_sources,
        audio_angle_map=podcast_audio_activity.parse_audio_angle_map(_typer_default(audio_angle_map)),
        audio_targets=podcast_audio_activity.parse_audio_targets(_typer_default(audio_target)),
        audio_sync=sync_payload,
        overlap=overlap_payload,
        angle_map=angle_map,
        reference_audio_by_angle=angle_map,
        max_timeline_ms=_parse_optional_seconds(duration_limit_seconds),
        fps=float(_typer_default(fps, 24.0) or 24.0),
        style=str(_typer_default(style, "balanced") or "balanced"),
        transcript_path=_typer_default(transcript),
        transcript_speaker_map=podcast_multicam.parse_speaker_mapping(_typer_default(transcript_speaker_map)),
        max_ranked_candidates=int(_typer_default(ranked_candidates, 8) or 8),
    )
    if str(write_analysis or "").strip():
        out_path = Path(str(write_analysis)).expanduser()
        if out_path.parent and not out_path.parent.exists():
            raise ValidationError(
                "Calibration analysis output directory does not exist.",
                details={"write_analysis": str(out_path), "parent": str(out_path.parent)},
            )
        out_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    recommendation = analysis.get("recommendation") if isinstance(analysis, dict) else None
    output(
        mutation_payload(
            action="multicam.audio_activity.calibrate",
            changed=False,
            target={"kind": "audio_activity_calibration"},
            recommendation=recommendation,
            ranked_candidates=analysis.get("ranked_candidates") if isinstance(analysis, dict) else [],
            diagnostics=analysis.get("diagnostics") if isinstance(analysis, dict) else {},
            candidate_count=analysis.get("candidate_count") if isinstance(analysis, dict) else 0,
            write_analysis=str(Path(str(write_analysis)).expanduser()) if str(write_analysis or "").strip() else None,
            message="Calibrated podcast multicam audio-activity switching thresholds.",
        )
    )


def _load_multicam_job_input(
    *,
    operation: str,
    job: str | None,
    job_json: str | None,
    angle_specs: list[str] | None,
    timeline_name: str | None,
    multicam_name: str | None,
    sync_mode: str | None = None,
    transcript_path: str | None = None,
    speaker_map: str | None = None,
    switch_by: str | None = None,
    audio_source_specs: list[str] | None = None,
    audio_angle_map: str | None = None,
    audio_target_specs: list[str] | None = None,
    audio_sync: str | None = None,
    sync_reference_audio: str | None = None,
    sync_reference_angle: str | None = None,
    audio_offsets_json: str | None = None,
    overlap_policy: str | None = None,
    overlap_angle: str | None = None,
    analysis_window_ms: int | None = None,
    activity_floor_db: float | None = None,
    activity_margin_db: float | None = None,
    dominance_margin_db: float | None = None,
    min_switch_ms: int | None = None,
    switch_delay_ms: int | None = None,
    max_silence_hold_ms: int | None = None,
    video_source_offset_specs: list[str] | None = None,
    allow_unresolved_targets: bool = False,
    replace_active_timeline: bool = False,
    allow_multicam_name_with_structured_job: bool = False,
) -> dict[str, object]:
    job = _typer_default(job)
    job_json = _typer_default(job_json)
    angle_specs = _typer_default(angle_specs)
    timeline_name = _typer_default(timeline_name)
    multicam_name = _typer_default(multicam_name)
    sync_mode = _typer_default(sync_mode)
    transcript_path = _typer_default(transcript_path)
    speaker_map = _typer_default(speaker_map)
    switch_by = _typer_default(switch_by)
    audio_source_specs = _typer_default(audio_source_specs)
    audio_angle_map = _typer_default(audio_angle_map)
    audio_target_specs = _typer_default(audio_target_specs)
    audio_sync = _typer_default(audio_sync)
    sync_reference_audio = _typer_default(sync_reference_audio)
    sync_reference_angle = _typer_default(sync_reference_angle)
    audio_offsets_json = _typer_default(audio_offsets_json)
    overlap_policy = _typer_default(overlap_policy)
    overlap_angle = _typer_default(overlap_angle)
    analysis_window_ms = _typer_default(analysis_window_ms)
    activity_floor_db = _typer_default(activity_floor_db)
    activity_margin_db = _typer_default(activity_margin_db)
    dominance_margin_db = _typer_default(dominance_margin_db)
    min_switch_ms = _typer_default(min_switch_ms)
    switch_delay_ms = _typer_default(switch_delay_ms)
    max_silence_hold_ms = _typer_default(max_silence_hold_ms)
    video_source_offset_specs = _typer_default(video_source_offset_specs)
    allow_unresolved_targets = bool(_typer_default(allow_unresolved_targets, False))
    replace_active_timeline = bool(_typer_default(replace_active_timeline, False))
    allow_multicam_name_with_structured_job = bool(_typer_default(allow_multicam_name_with_structured_job, False))
    has_structured_job = bool(job) or bool(job_json)
    convenience_multicam_name = None if allow_multicam_name_with_structured_job else multicam_name
    has_convenience_input = _has_convenience_multicam_input(
        angle_specs,
        timeline_name,
        convenience_multicam_name,
        sync_mode,
        transcript_path,
        speaker_map,
        switch_by,
        audio_source_specs,
        audio_angle_map,
        audio_target_specs,
        audio_sync,
        sync_reference_audio,
        sync_reference_angle,
        audio_offsets_json,
        overlap_policy,
        overlap_angle,
        analysis_window_ms,
        activity_floor_db,
        activity_margin_db,
        dominance_margin_db,
        min_switch_ms,
        switch_delay_ms,
        max_silence_hold_ms,
        video_source_offset_specs,
    )

    if has_structured_job:
        if has_convenience_input:
            raise ValidationError(
                "Provide either --job/--job-json or convenience multicam flags, not both.",
                details={"operation": operation},
            )
        return multicam_engine.load_multicam_job(job_path=job, job_json=job_json)

    return _build_multicam_convenience_job(
        operation=operation,
        angle_specs=angle_specs,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        sync_mode=sync_mode,
        transcript_path=transcript_path,
        speaker_map=speaker_map,
        switch_by=switch_by,
        audio_source_specs=audio_source_specs,
        audio_angle_map=audio_angle_map,
        audio_target_specs=audio_target_specs,
        audio_sync=audio_sync,
        sync_reference_audio=sync_reference_audio,
        sync_reference_angle=sync_reference_angle,
        audio_offsets_json=audio_offsets_json,
        overlap_policy=overlap_policy,
        overlap_angle=overlap_angle,
        analysis_window_ms=analysis_window_ms,
        activity_floor_db=activity_floor_db,
        activity_margin_db=activity_margin_db,
        dominance_margin_db=dominance_margin_db,
        min_switch_ms=min_switch_ms,
        switch_delay_ms=switch_delay_ms,
        max_silence_hold_ms=max_silence_hold_ms,
        video_source_offset_specs=video_source_offset_specs,
        allow_unresolved_targets=allow_unresolved_targets,
        replace_active_timeline=replace_active_timeline,
    )
