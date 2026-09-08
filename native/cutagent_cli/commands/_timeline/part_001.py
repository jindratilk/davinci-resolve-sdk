"""Timeline commands — CRUD, playhead, markers, tracks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

import typer
from typer.core import TyperGroup

from ..connection import get_connection
from ..errors import APICallFailed, ConfirmationRequired, InvalidTimeReference, ValidationError, handle_errors
from ..external_tools import resolve_tool
from ..output import dry_run_message, is_agent_mode, is_dry_run, is_lean, is_machine_mode, mutation_payload, output, set_capability_context, set_execution_engine, set_recoverability, set_verification_status, success
from ..policy import enforce_mutation_policy
from ..core import (
    clip_ops,
    color_ops,
    multicam_engine,
    speed_ramp_db,
    timeline_clip_color,
    timeline_item_duration_db,
    timeline_item_move_db,
    timeline_inspection_export,
    timeline_layer_ops,
    timeline_layout,
    timeline_markers,
    timeline_ops,
    timeline_overlay_stack,
    timeline_sync,
)
from ..core.resolve_state_lock import exclusive_resolve_state_operation
from ..utils.time_ref import parse_record_frame, parse_source_frame

class _TimelineTyperGroup(TyperGroup):
    """Route batch-style aliases without changing existing single commands."""

    def invoke(self, ctx):
        if ctx._protected_args:
            args = [*ctx._protected_args, *ctx.args]
            if len(args) >= 2 and args[0] == "frame-export" and args[1] == "batch":
                ctx._protected_args = ["frame-export-batch"]
                ctx.args = args[2:]
        return super().invoke(ctx)


app = typer.Typer(help="Timeline operations.", cls=_TimelineTyperGroup)


def _sdk_private_digest_value(value: object) -> object:
    if isinstance(value, bytes):
        return {"blob_sha256": hashlib.sha256(value).hexdigest(), "blob_size": len(value)}
    if isinstance(value, dict):
        return {
            str(key): _sdk_private_digest_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_sdk_private_digest_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _sdk_private_value_digest(value: object) -> str:
    encoded = json.dumps(
        _sdk_private_digest_value(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sdk_bounded_multicam_text(value: object, *, field: str, maximum_code_units: int) -> str:
    normalized = str(value or "").strip()
    code_units = len(normalized.encode("utf-16-le")) // 2
    if not normalized or code_units > maximum_code_units:
        raise ValidationError(
            f"{field} must contain 1 to {maximum_code_units} UTF-16 code units.",
            details={"field": field, "maximum_code_units": maximum_code_units, "actual_code_units": code_units},
        )
    return normalized


def _sdk_multicam_source_evidence(conn, source_ids: set[str]) -> dict[str, dict[str, str]]:
    matches_by_id: dict[str, list[dict[str, object]]] = {}
    matches_by_unique_id: dict[str, list[dict[str, object]]] = {}
    for match in multicam_engine.media_pool.collect_append_media_matches(conn):
        media_id = str(match.get("media_id") or "")
        if media_id in source_ids:
            matches_by_id.setdefault(media_id, []).append(match)
        clip = match.get("clip")
        getter = getattr(clip, "GetUniqueId", None)
        try:
            unique_id = str(getter() or "") if callable(getter) else ""
        except Exception:
            unique_id = ""
        if unique_id in source_ids:
            matches_by_unique_id.setdefault(unique_id, []).append(match)
    evidence: dict[str, dict[str, str]] = {}
    for source_id in sorted(source_ids):
        matches = list(matches_by_id.get(source_id) or [])
        if not matches:
            matches = list(matches_by_unique_id.get(source_id) or [])
        if len(matches) != 1:
            raise ValidationError(
                "Multicam SDK inspection could not resolve an exact Media Pool source identity.",
                details={"source_media_id": source_id, "match_count": len(matches)},
            )
        match = matches[0]
        clip = match.get("clip")
        properties = match.get("props") if isinstance(match.get("props"), dict) else None
        if properties is None:
            getter = getattr(clip, "GetClipProperty", None)
            properties = getter() if callable(getter) else None
        metadata_getter = getattr(clip, "GetMetadata", None)
        metadata = metadata_getter() if callable(metadata_getter) else None
        if not isinstance(properties, dict) or not isinstance(metadata, dict):
            raise ValidationError(
                "Multicam SDK inspection requires source property and metadata readback.",
                details={"source_media_id": source_id},
            )
        evidence[source_id] = {
            "native_id": str(match.get("media_id") or source_id),
            "properties_digest": _sdk_private_value_digest(properties),
            "metadata_digest": _sdk_private_value_digest(metadata),
        }
    return evidence


def _sdk_multicam_summary(conn, multicam_name: str) -> dict[str, object]:
    """Return private native evidence for bridge-side public normalization."""
    inspected = multicam_engine.inspect_multicam(conn, multicam_name=multicam_name)
    multicam_clip = multicam_engine.media_pool.find_clip(conn, multicam_name)
    video_mapping = list(inspected.get("video_source_mapping") or [])
    audio_mapping = list(inspected.get("audio_source_mapping") or [])
    source_ids = {
        str(item.get("source_media_id"))
        for item in [*video_mapping, *audio_mapping]
        if item.get("source_media_id")
    }
    source_evidence = _sdk_multicam_source_evidence(conn, source_ids)
    binding_angles = {
        int(angle.get("angle_index") or 0): angle
        for angle in inspected.get("angles") or []
    }
    angles = []
    for angle in inspected.get("angle_order") or []:
        angle_index = angle.get("angle_index")
        mappings = [
            item for item in video_mapping
            if item.get("angle_index") == angle_index and item.get("source_media_id")
        ]
        audio_mappings = [
            item for item in audio_mapping
            if item.get("angle_index") == angle_index and item.get("source_media_id")
        ]
        mappings.sort(key=lambda item: (int(item.get("item_index") or 0), int(item.get("start_frame") or 0)))
        audio_mappings.sort(key=lambda item: (int(item.get("item_index") or 0), int(item.get("start_frame") or 0)))

        def source_summary(item):
            source_id = str(item.get("source_media_id") or "")
            native_id = str(source_evidence[source_id].get("native_id") or source_id)
            return {
                "name": _sdk_bounded_multicam_text(
                    item.get("clip_name"), field="Multicam source name", maximum_code_units=1024
                ),
                "native_id": native_id,
                **({"database_native_id": source_id} if native_id != source_id else {}),
                "track_native_id": str(item.get("track_id") or ""),
                "item_index": int(item.get("item_index") or 0),
                "start_frame": int(item.get("start_frame") or 0),
                "duration_frames": int(item.get("duration_frames") or 0),
                "source_in_frame": int(item.get("source_in_frame") or 0),
                "selector_index": item.get("current_selector_idx"),
                "selector_signature": item.get("selector_signature"),
                "grade_revision_digest": item.get("grade_revision_digest"),
                "properties_digest": source_evidence[source_id]["properties_digest"],
                "metadata_digest": source_evidence[source_id]["metadata_digest"],
            }

        binding_angle = binding_angles.get(int(angle_index or 0))
        if not isinstance(binding_angle, dict):
            raise ValidationError(
                "Multicam SDK inspection did not return per-angle track state.",
                details={"angle_index": angle_index},
            )
        if not isinstance(binding_angle.get("video_enabled"), bool) or not isinstance(binding_angle.get("audio_enabled"), bool):
            raise ValidationError(
                "Multicam SDK inspection returned invalid per-angle enabled state.",
                details={"angle_index": angle_index},
            )
        angles.append({
            "angle_index": angle_index,
            "label": _sdk_bounded_multicam_text(
                binding_angle.get("video_track_name") or angle.get("ui_label"), field="Multicam angle label", maximum_code_units=256
            ),
            "video_label": _sdk_bounded_multicam_text(binding_angle.get("video_track_name") or angle.get("ui_label"), field="Multicam video angle label", maximum_code_units=256),
            "audio_label": _sdk_bounded_multicam_text(binding_angle.get("audio_track_name") or angle.get("ui_label"), field="Multicam audio angle label", maximum_code_units=256),
            "video_enabled": bool(binding_angle.get("video_enabled")),
            "audio_enabled": bool(binding_angle.get("audio_enabled")),
            "sources": [source_summary(item) for item in mappings],
            "audio_sources": [source_summary(item) for item in audio_mappings],
        })
    return {
        "name": _sdk_bounded_multicam_text(
            inspected.get("multicam_name"), field="Multicam name", maximum_code_units=1024
        ),
        "native_id": timeline_ops.documented_sdk_media_pool_id(multicam_clip),
        "angles": angles,
    }


def _load_clip_color_batch_entries(path: str) -> list[dict[str, object]]:
    input_path = Path(path).expanduser()
    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(
            "Timeline clip-color batch input file was not found.",
            details={"path": str(input_path)},
            recoverability="not_applicable",
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Timeline clip-color batch input file is not valid JSON.",
            details={"path": str(input_path), "line": exc.lineno, "column": exc.colno},
            recoverability="not_applicable",
        ) from exc

    if isinstance(raw, dict):
        for key in ("segments", "items", "entries"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if not isinstance(raw, list):
        raise ValidationError(
            "Timeline clip-color batch input must be a JSON array or an object with a segments/items/entries array.",
            details={"path": str(input_path)},
            recoverability="not_applicable",
        )

    entries: list[dict[str, object]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValidationError(
                "Each timeline clip-color batch entry must be a JSON object.",
                details={"path": str(input_path), "index": index, "entry": entry},
                recoverability="not_applicable",
            )
        entries.append(dict(entry))
    return entries


def _load_timeline_item_duration_batch_entries(path: str) -> list[dict[str, object]]:
    input_path = Path(path).expanduser()
    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(
            "Timeline item duration batch input file was not found.",
            details={"path": str(input_path)},
            recoverability="not_applicable",
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Timeline item duration batch input file is not valid JSON.",
            details={"path": str(input_path), "line": exc.lineno, "column": exc.colno},
            recoverability="not_applicable",
        ) from exc

    if isinstance(raw, dict):
        for key in ("items", "entries", "updates", "durations"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if not isinstance(raw, list):
        raise ValidationError(
            "Timeline item duration batch input must be a JSON array or an object with an items/entries/updates/durations array.",
            details={"path": str(input_path)},
            recoverability="not_applicable",
        )

    entries: list[dict[str, object]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValidationError(
                "Timeline item duration batch entries must be JSON objects.",
                details={"path": str(input_path), "index": index},
                recoverability="not_applicable",
            )
        entries.append(entry)
    return entries


def _load_json_object_entries(
    *,
    path: str | None,
    raw_json: str | None,
    alt_raw_json: str | None,
    wrapper_keys: tuple[str, ...],
    label: str,
) -> list[dict[str, object]]:
    provided = [value for value in (path, raw_json, alt_raw_json) if value is not None]
    if len(provided) != 1:
        raise ValidationError(
            f"{label} requires exactly one of --batch, --batch-json, or --spec-json.",
            details={"batch": path, "batch_json": raw_json, "spec_json": alt_raw_json},
            recoverability="not_applicable",
        )

    try:
        if path is not None:
            input_path = Path(path).expanduser()
            source = input_path.read_text(encoding="utf-8")
        else:
            source = raw_json if raw_json is not None else alt_raw_json
        raw = json.loads(source)
    except FileNotFoundError as exc:
        raise ValidationError(
            f"{label} input file was not found.",
            details={"path": str(Path(path).expanduser()) if path else None},
            recoverability="not_applicable",
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"{label} input is not valid JSON.",
            details={"line": exc.lineno, "column": exc.colno, "path": str(Path(path).expanduser()) if path else None},
            recoverability="not_applicable",
        ) from exc

    if isinstance(raw, dict):
        for key in wrapper_keys:
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if not isinstance(raw, list):
        raise ValidationError(
            f"{label} input must be a JSON array or an object with one of: {', '.join(wrapper_keys)}.",
            details={"path": str(Path(path).expanduser()) if path else None},
            recoverability="not_applicable",
        )
    entries: list[dict[str, object]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValidationError(
                f"Each {label.lower()} entry must be a JSON object.",
                details={"index": index, "entry": entry},
                recoverability="not_applicable",
            )
        entries.append(dict(entry))
    return entries


def _resolve_thumbnail_output_file_path(output_path: str, *, require_parent: bool = True) -> Path:
    raw = str(output_path).strip()
    if not raw:
        raise ValidationError(
            "--output must not be empty.",
            details={"output_path": output_path},
            recoverability="not_applicable",
        )
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve(strict=False)
    if path.exists() and path.is_dir():
        raise ValidationError(
            "Output path must be a file path, not a directory.",
            details={"output_path": str(path)},
            recoverability="not_applicable",
        )
    if require_parent and not path.parent.is_dir():
        raise ValidationError(
            "Output directory does not exist.",
            details={"output_path": str(path), "parent": str(path.parent)},
            recoverability="not_applicable",
        )
    return path


def _thumbnail_file_metadata(path: Path) -> dict[str, object]:
    size = path.stat().st_size
    metadata: dict[str, object] = {
        "exists": path.is_file(),
        "bytes": size,
        "format": None,
        "width": None,
        "height": None,
    }
    with path.open("rb") as fh:
        header = fh.read(32)
    if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
        metadata.update(
            {
                "format": "png",
                "width": int.from_bytes(header[16:20], "big"),
                "height": int.from_bytes(header[20:24], "big"),
            }
        )
    elif header.startswith(b"\xff\xd8"):
        metadata["format"] = "jpeg"
    return metadata


def _workspace_relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _resolve_output_directory(path: str, *, create: bool = True) -> Path:
    raw = str(path or "").strip()
    if not raw:
        raise ValidationError("--out-dir must not be empty.", details={"out_dir": path})
    resolved = Path(raw).expanduser()
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    resolved = resolved.resolve(strict=False)
    if resolved.exists() and not resolved.is_dir():
        raise ValidationError("--out-dir must be a directory path.", details={"out_dir": str(resolved)})
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _parse_frame_refs(frames: str) -> list[str]:
    refs = [part.strip() for part in str(frames or "").split(",") if part.strip()]
    if not refs:
        raise ValidationError("--frames must contain at least one frame/time reference.", details={"frames": frames})
    return refs


def _preflight_timeline_frame_refs(conn, frame_refs: list[str]) -> list[dict[str, object]]:
    try:
        start_frame = int(conn.timeline.GetStartFrame())
        end_frame = int(conn.timeline.GetEndFrame())
    except Exception as exc:
        raise InvalidTimeReference(
            "The active timeline frame range could not be read before export.",
            details={"requested": list(frame_refs), "time_domain": "record", "error": str(exc)},
            recoverability="not_applicable",
        ) from exc
    if end_frame <= start_frame:
        raise InvalidTimeReference(
            "The active timeline returned an invalid frame range.",
            details={
                "requested": list(frame_refs),
                "time_domain": "record",
                "allowed_range": {
                    "start_frame": start_frame,
                    "end_frame_exclusive": end_frame,
                    "last_frame": end_frame - 1,
                },
            },
            recoverability="not_applicable",
        )

    targets: list[dict[str, object]] = []
    invalid_targets: list[dict[str, object]] = []
    for frame_ref in frame_refs:
        target = dict(timeline_ops.resolve_playhead_target(conn, frame_ref))
        targets.append(target)
        target_frame = int(target["target_frame"])
        if target_frame < start_frame or target_frame >= end_frame:
            invalid_targets.append(target)

    if invalid_targets:
        raise InvalidTimeReference(
            "One or more requested record-frame positions are outside the active timeline.",
            details={
                "requested": list(frame_refs),
                "requested_targets": targets,
                "invalid_targets": invalid_targets,
                "allowed_range": {
                    "start_frame": start_frame,
                    "end_frame_exclusive": end_frame,
                    "last_frame": end_frame - 1,
                },
                "time_domain": "record",
            },
            recoverability="not_applicable",
        )
    return targets


def _safe_ref_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return token.strip("._") or "frame"


def _frame_output_path(out_dir: Path, *, prefix: str, index: int, frame_ref: str, extension: str) -> Path:
    ext = str(extension or "png").lower().lstrip(".")
    if ext not in {"png", "jpg", "jpeg"}:
        raise ValidationError("Frame export extension must be png, jpg, or jpeg.", details={"extension": extension})
    return out_dir / f"{prefix}_{index:03d}_{_safe_ref_token(frame_ref)}.{ext}"


def _export_current_frame_as_still(
    conn,
    *,
    resolved_path: Path,
    requested_output_path: str,
    error_message: str,
) -> dict[str, object]:
    try:
        with color_ops._with_required_page(conn, "color"):
            ok = conn.project.ExportCurrentFrameAsStill(str(resolved_path))
    except APICallFailed:
        raise
    except Exception as exc:
        raise APICallFailed(
            error_message,
            details={
                "output_path": str(resolved_path),
                "requested_output_path": requested_output_path,
                "api_call": "Project.ExportCurrentFrameAsStill",
                "required_page": "color",
                "error": str(exc),
            },
        ) from exc
    if not ok:
        raise APICallFailed(
            error_message,
            details={
                "output_path": str(resolved_path),
                "requested_output_path": requested_output_path,
                "api_call": "Project.ExportCurrentFrameAsStill",
                "api_result": ok,
                "required_page": "color",
                "ui": _probe_current_item_ui_context(),
            },
        )
    if not resolved_path.is_file():
        raise APICallFailed(
            "Frame export reported success but output file was not created.",
            details={
                "output_path": str(resolved_path),
                "requested_output_path": requested_output_path,
                "api_call": "Project.ExportCurrentFrameAsStill",
                "api_result": ok,
                "required_page": "color",
            },
        )
    return _thumbnail_file_metadata(resolved_path)


def _set_frame_export_playhead(conn, frame_ref: str) -> dict[str, object]:
    """Set and verify the export target, with one bounded transient retry."""
    def _set_exact() -> dict[str, object]:
        result = dict(
            timeline_ops.set_playhead(
                conn,
                frame_ref,
                return_details=True,
                frame_tolerance=0,
            )
        )
        if int(result.get("final_frame")) != int(result.get("target_frame")):
            raise APICallFailed(
                "Playhead did not settle on the exact frame required for export.",
                details={
                    "api_call": "Timeline.SetCurrentTimecode",
                    "requested": frame_ref,
                    "target_frame": result.get("target_frame"),
                    "actual_frame": result.get("final_frame"),
                },
            )
        return result

    try:
        return _set_exact()
    except APICallFailed as exc:
        details = exc.details if isinstance(exc.details, dict) else {}
        if details.get("api_call") != "Timeline.SetCurrentTimecode":
            raise
        time.sleep(0.1)
        return _set_exact()


def _export_single_timeline_frame(
    conn,
    *,
    frame_ref: str,
    resolved_path: Path,
    requested_output_path: str,
) -> dict[str, object]:
    _preflight_timeline_frame_refs(conn, [frame_ref])
    original_playhead = timeline_ops.get_playhead(conn)
    restored = False
    restore_error: str | None = None
    metadata: dict[str, object] = {}
    target: dict[str, object]
    try:
        # ExportCurrentFrameAsStill is Color-page owned. Switch pages before moving
        # the playhead so the Color viewer is settled on the requested record frame;
        # switching inside the exporter can otherwise leave it on the prior frame.
        with color_ops._with_required_page(conn, "color"):
            target = _set_frame_export_playhead(conn, frame_ref)
            metadata = _export_current_frame_as_still(
                conn,
                resolved_path=resolved_path,
                requested_output_path=requested_output_path,
                error_message="Failed to export frame from requested timeline position.",
            )
    finally:
        original_tc = original_playhead.get("timecode")
        if original_tc:
            try:
                restored_target = _set_frame_export_playhead(conn, str(original_tc))
                if int(restored_target["final_frame"]) != int(original_playhead["frame"]):
                    raise APICallFailed(
                        "The original playhead frame could not be restored exactly.",
                        details={
                            "api_call": "Timeline.SetCurrentTimecode",
                            "target_frame": original_playhead.get("frame"),
                            "actual_frame": restored_target.get("final_frame"),
                        },
                    )
                restored = True
            except Exception as exc:
                restore_error = str(exc)
    return {
        "original_playhead": original_playhead,
        "target": target,
        "restored_playhead": restored,
        "restore_warning": restore_error,
        **metadata,
    }


def _export_frame_sequence(
    conn,
    *,
    frame_refs: list[str],
    out_dir: Path,
    prefix: str,
    extension: str,
) -> dict[str, object]:
    with exclusive_resolve_state_operation(operation="timeline.frame_export.sequence"):
        _preflight_timeline_frame_refs(conn, frame_refs)
        out_dir.mkdir(parents=True, exist_ok=True)
        original_playhead = timeline_ops.get_playhead(conn)
        restored = False
        restore_error: str | None = None
        frames: list[dict[str, object]] = []
        try:
            for index, frame_ref in enumerate(frame_refs):
                resolved_path = _frame_output_path(out_dir, prefix=prefix, index=index, frame_ref=frame_ref, extension=extension)
                target = _set_frame_export_playhead(conn, frame_ref)
                metadata = _export_current_frame_as_still(
                    conn,
                    resolved_path=resolved_path,
                    requested_output_path=str(resolved_path),
                    error_message="Failed to export frame from requested timeline position.",
                )
                frames.append(
                    {
                        "index": index,
                        "requested_at": frame_ref,
                        "output_path": str(resolved_path),
                        "visual_check_path": _workspace_relative_path(resolved_path),
                        "target": target,
                        "exported": True,
                        "verified": True,
                        **metadata,
                    }
                )
        finally:
            original_tc = original_playhead.get("timecode")
            if original_tc:
                try:
                    restored_target = _set_frame_export_playhead(conn, str(original_tc))
                    if int(restored_target["final_frame"]) != int(original_playhead["frame"]):
                        raise APICallFailed(
                            "The original playhead frame could not be restored exactly.",
                            details={
                                "api_call": "Timeline.SetCurrentTimecode",
                                "target_frame": original_playhead.get("frame"),
                                "actual_frame": restored_target.get("final_frame"),
                            },
                        )
                    restored = True
                except Exception as exc:
                    restore_error = str(exc)
    return {
        "frames": frames,
        "original_playhead": original_playhead,
        "restored_playhead": restored,
        "restore_warning": restore_error,
    }


def _write_contact_sheet(frame_paths: list[Path], output_path: Path, *, columns: int = 3, tile_width: int = 480) -> dict[str, object]:
    if not frame_paths:
        raise ValidationError("Contact sheet requires at least one exported frame.")
    if columns < 1:
        raise ValidationError("--contact-columns must be 1 or greater.", details={"columns": columns})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    first_meta = _thumbnail_file_metadata(frame_paths[0])
    source_w = int(first_meta.get("width") or 1920)
    source_h = int(first_meta.get("height") or 1080)
    tile_h = max(1, int(round(tile_width * source_h / max(source_w, 1))))
    ffmpeg = resolve_tool("ffmpeg")
    cmd = [ffmpeg, "-y"]
    for path in frame_paths:
        cmd.extend(["-i", str(path)])
    if len(frame_paths) == 1:
        filter_complex = f"[0:v]scale={tile_width}:{tile_h}[out]"
    else:
        filters = [f"[{index}:v]scale={tile_width}:{tile_h}[v{index}]" for index in range(len(frame_paths))]
        labels = "".join(f"[v{index}]" for index in range(len(frame_paths)))
        layout = "|".join(f"{(index % columns) * tile_width}_{(index // columns) * tile_h}" for index in range(len(frame_paths)))
        filters.append(f"{labels}xstack=inputs={len(frame_paths)}:layout={layout}:fill=0x05090d[out]")
        filter_complex = ";".join(filters)
    cmd.extend(["-filter_complex", filter_complex, "-map", "[out]", "-frames:v", "1", str(output_path)])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not output_path.is_file():
        raise APICallFailed(
            "ffmpeg contact sheet generation failed.",
            details={"cmd": cmd, "returncode": proc.returncode, "stderr": (proc.stderr or "")[-2000:]},
        )
    return {
        "output_path": str(output_path),
        "visual_check_path": _workspace_relative_path(output_path),
        "columns": columns,
        "tile_width": tile_width,
        "tile_height": tile_h,
        **_thumbnail_file_metadata(output_path),
    }


def _write_preview_video(frame_paths: list[Path], output_path: Path, *, fps: float) -> dict[str, object]:
    if not frame_paths:
        raise ValidationError("Preview export requires at least one exported frame.")
    if fps <= 0:
        raise ValidationError("--fps must be greater than 0.", details={"fps": fps})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sequence_dir = output_path.parent / f".{output_path.stem}_frames"
    if sequence_dir.exists():
        shutil.rmtree(sequence_dir)
    sequence_dir.mkdir(parents=True, exist_ok=True)
    try:
        for index, path in enumerate(frame_paths):
            shutil.copyfile(path, sequence_dir / f"frame_{index:04d}.png")
        ffmpeg = resolve_tool("ffmpeg")
        suffix = output_path.suffix.lower()
        cmd = [
            ffmpeg,
            "-y",
            "-framerate",
            f"{fps:g}",
            "-i",
            str(sequence_dir / "frame_%04d.png"),
        ]
        if suffix == ".gif":
            cmd.extend(["-vf", "fps=12,scale=960:-1:flags=lanczos", str(output_path)])
        else:
            cmd.extend(["-vf", "format=yuv420p", "-movflags", "+faststart", str(output_path)])
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0 or not output_path.is_file():
            raise APICallFailed(
                "ffmpeg preview export failed.",
                details={"cmd": cmd, "returncode": proc.returncode, "stderr": (proc.stderr or "")[-2000:]},
            )
    finally:
        shutil.rmtree(sequence_dir, ignore_errors=True)
    return {
        "output_path": str(output_path),
        "visual_check_path": _workspace_relative_path(output_path),
        "fps": fps,
        "frame_count": len(frame_paths),
        "bytes": output_path.stat().st_size,
        "format": "gif" if output_path.suffix.lower() == ".gif" else "video",
    }


def _compound_create_dry_run_payload(
    *,
    in_ref: str,
    out_ref: str,
    track_type: str,
    track: int,
    name: Optional[str],
    start_tc: Optional[str],
) -> dict[str, object]:
    normalized_track_type = str(track_type).strip().lower()
    if normalized_track_type not in {"video", "audio", "subtitle", "all"}:
        raise ValidationError(
            "Track type must be one of: video, audio, subtitle, all.",
            details={"track_type": track_type},
        )
    preview_fps = 24.0
    preview_start_frame = 0
    start_frame = parse_record_frame(in_ref, preview_fps, preview_start_frame)
    end_frame = parse_record_frame(out_ref, preview_fps, preview_start_frame)
    if end_frame <= start_frame:
        raise ValidationError(
            "Compound clip out must be after in.",
            details={"in": in_ref, "out": out_ref},
        )
    clip_info = {}
    if name:
        clip_info["name"] = name
    if start_tc:
        clip_info["startTimecode"] = start_tc
    return mutation_payload(
        action="timeline.compound_create",
        changed=False,
        target={"kind": "compound_clip", "name": name},
        range={
            "in": in_ref,
            "out": out_ref,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "preview_fps": preview_fps,
            "preview_start_frame": preview_start_frame,
        },
        track_type=normalized_track_type,
        track_index=track,
        clip_info=clip_info,
        message="DRY-RUN: Would create a compound clip from the requested record-domain range.",
    )


def _current_item_context(conn) -> dict[str, object]:
    context: dict[str, object] = {
        "timeline": None,
        "fps": getattr(conn, "fps", None),
        "start_frame": getattr(conn, "start_frame", None),
    }
    try:
        context["timeline"] = conn.timeline.GetName()
    except Exception:
        pass
    try:
        context["playhead"] = timeline_ops.get_playhead(conn)
    except Exception:
        pass
    return context


def _timeline_readback_context(conn) -> dict[str, object]:
    context = _current_item_context(conn)
    track_counts: dict[str, int] = {}
    for track_type in ("video", "audio", "subtitle"):
        try:
            track_counts[track_type] = int(conn.timeline.GetTrackCount(track_type) or 0)
        except Exception:
            track_counts[track_type] = 0
    context["track_counts"] = track_counts
    return context


def _probe_current_item_ui_context() -> dict[str, object]:
    try:
        from .utility import _probe_resolve_ui_state

        return _probe_resolve_ui_state()
    except Exception as exc:
        return {
            "available": False,
            "blocked": None,
            "active_modal": None,
            "probe": "macos_system_events",
            "error": str(exc),
        }


def _attach_current_item_ui_context(data: dict[str, object], ui_state: dict[str, object] | None = None) -> None:
    if ui_state is None:
        ui_state = _probe_current_item_ui_context()
    data["ui"] = ui_state
    ui_blocked = bool(ui_state.get("blocked"))
    ui_probe_uncertain = ui_state.get("blocked") is None or bool(ui_state.get("error"))
    data["ui_blocked"] = ui_blocked
    data["active_modal"] = ui_state.get("active_modal")
    data["visual_readback_available"] = not ui_blocked and not ui_probe_uncertain
    if ui_blocked or ui_probe_uncertain:
        set_verification_status("pending_manual")
        set_recoverability("manual")


def _ui_readback_summary(ui_state: dict[str, object]) -> dict[str, object]:
    ui_blocked = bool(ui_state.get("blocked"))
    ui_probe_uncertain = ui_state.get("blocked") is None or bool(ui_state.get("error"))
    return {
        "ui_blocked": ui_blocked,
        "active_modal": ui_state.get("active_modal"),
        "visual_readback_available": not ui_blocked and not ui_probe_uncertain,
    }


def _attach_duration_readback_context(data: dict[str, object], conn) -> None:
    for key, value in _timeline_readback_context(conn).items():
        data.setdefault(key, value)
    fps = data.get("fps")
    start_frame = data.get("start_frame")
    end_frame = data.get("end_frame")
    duration_seconds = data.get("duration_seconds")
    try:
        if end_frame is not None and start_frame is not None:
            data["total_frames"] = int(end_frame) - int(start_frame)
        elif duration_seconds is not None and fps:
            data["total_frames"] = round(float(duration_seconds) * float(fps))
    except Exception:
        pass


def _timeline_duplicate_dry_run_payload(*, new_name: str, source: Optional[str]) -> dict[str, object]:
    normalized_new_name = str(new_name or "").strip()
    if not normalized_new_name:
        raise ValidationError(
            "Timeline duplicate name is required.",
            details={"new_name": new_name},
            recoverability="not_applicable",
        )
    normalized_source = str(source).strip() if source is not None else None
    if normalized_source == "":
        normalized_source = None
    payload = mutation_payload(
        action="timeline.duplicate",
        changed=False,
        target={"kind": "timeline", "name": normalized_new_name},
        source={"kind": "timeline", "name": normalized_source} if normalized_source else {"kind": "timeline", "name": "current"},
        message=f"DRY-RUN: Would duplicate timeline to '{normalized_new_name}'.",
    )
    return payload


def _timeline_rename_dry_run_payload(*, new_name: str, source: Optional[str]) -> dict[str, object]:
    normalized_new_name = str(new_name or "").strip()
    if not normalized_new_name:
        raise ValidationError(
            "Timeline rename target name is required.",
            details={"new_name": new_name},
            recoverability="not_applicable",
        )
    normalized_source = str(source).strip() if source is not None else None
    if normalized_source == "":
        raise ValidationError(
            "Timeline rename source name must not be empty.",
            details={"source_name": source},
            recoverability="not_applicable",
        )
    return mutation_payload(
        action="timeline.rename",
        changed=False,
        target={"kind": "timeline", "name": normalized_new_name},
        source=(
            {"kind": "timeline", "name": normalized_source}
            if normalized_source
            else {"kind": "timeline", "name": "current"}
        ),
        message=f"DRY-RUN: Would rename timeline to '{normalized_new_name}'.",
    )


def _caption_route_prompt(requested_as: str) -> dict[str, object]:
    return {
        "decision_required": True,
        "requested_as": requested_as,
        "question": "Do you want a subtitle track or Fusion Text+?",
        "options": [
            {
                "id": "subtitle_track",
                "label": "Subtitle track",
                "description": "Use real subtitle-track items for subtitle export and caption workflows.",
                "next_command_hint": "cutagent timeline subtitle list|export or cutagent timeline auto-caption",
            },
            {
                "id": "fusion_text_plus",
                "label": "Fusion Text+",
                "description": "Use styled on-screen Text+/Fusion overlays for visual captions.",
                "next_command_hint": "cutagent text insert or cutagent text insert-template",
            },
        ],
    }


def _timeline_items_delete_dry_run_payload(
    *,
    timeline_name: str | None,
    track_type: str,
    track_index: int | None,
    start_frame: str | None,
    end_frame: str | None,
    match: str,
    allow_empty: bool,
    force: bool,
) -> dict[str, object]:
    normalized_track_type = timeline_ops.normalize_timeline_item_track_type(track_type)
    normalized_match = timeline_ops.normalize_timeline_item_delete_match(match)
    normalized_track_index = timeline_ops.validate_timeline_track_index(track_index) if track_index is not None else None
    preview_fps = 24.0
    preview_start_frame = 0
    resolved_start = parse_record_frame(str(start_frame), preview_fps, preview_start_frame) if start_frame is not None else None
    resolved_end = parse_record_frame(str(end_frame), preview_fps, preview_start_frame) if end_frame is not None else None
    if resolved_start is not None and resolved_end is not None and resolved_end <= resolved_start:
        raise ValidationError(
            "Timeline item delete end frame must be after start frame.",
            details={"start_frame": start_frame, "end_frame": end_frame, "resolved_start_frame": resolved_start, "resolved_end_frame": resolved_end},
            recoverability="not_applicable",
        )
    wide_delete = resolved_start is None and resolved_end is None
    return mutation_payload(
        action="timeline.items.delete",
        changed=False,
        target={"kind": "timeline", "name": timeline_name or "current"},
        filters={
            "timeline": timeline_name,
            "track_type": normalized_track_type,
            "track_index": normalized_track_index,
            "start_frame_ref": start_frame,
            "end_frame_ref": end_frame,
            "start_frame": resolved_start,
            "end_frame": resolved_end,
            "match": normalized_match,
            "allow_empty": bool(allow_empty),
            "force": bool(force),
        },
        dry_run=True,
        command_intent={
            "collect": "Timeline.GetItemListInTrack",
            "delete": "Timeline.DeleteClips(items, False)",
            "ripple": False,
            "delete_tracks": False,
            "requires_force_for_mutation": bool(wide_delete),
            "preview_fps": preview_fps,
            "preview_start_frame": preview_start_frame,
        },
        message="DRY-RUN: Would delete matching timeline items without deleting tracks or rippling.",
    )


@app.command("list")
@handle_errors
def list_timelines():
    """List all timelines in the current project."""
    ui_state = _probe_current_item_ui_context()
    conn = get_connection(require_project=True)
    rows = timeline_ops.list_timelines(conn)
    ui_summary = _ui_readback_summary(ui_state)
    for row in rows:
        row.update(ui_summary)
    if not ui_summary["visual_readback_available"]:
        set_verification_status("pending_manual")
        set_recoverability("manual")
    output(rows, columns=[("index", "#"), ("name", "Name"), ("fps", "FPS"), ("current", "Current")],
           title="Timelines", quiet_key="name")


@app.command()
@handle_errors
def info():
    """Show info about the current timeline."""
    ui_state = _probe_current_item_ui_context()
    conn = get_connection(require_timeline=True)
    data = timeline_ops.get_timeline_info(conn)
    duration_info = timeline_ops.get_timeline_duration(conn)
    _attach_duration_readback_context(duration_info, conn)
    data["duration_info"] = duration_info
    if "playhead" in duration_info:
        data["playhead"] = duration_info["playhead"]
    if "track_counts" in duration_info:
        data["track_counts"] = duration_info["track_counts"]
    if "total_frames" in duration_info:
        data["total_frames"] = duration_info["total_frames"]
    _attach_current_item_ui_context(data, ui_state)
    output(data, title="Timeline Info")


@app.command()
@handle_errors
def create(
    name: str = typer.Argument(..., help="Timeline name"),
    width: Optional[int] = typer.Option(None, help="Resolution width"),
    height: Optional[int] = typer.Option(None, help="Resolution height"),
    fps: Optional[float] = typer.Option(None, help="Frame rate"),
):
    """Create a new empty timeline."""
    enforce_mutation_policy(
        "timeline.create",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would create timeline: {name} ({width}x{height} @ {fps}fps)" if width else f"Would create timeline: {name}")
        return
    conn = get_connection(require_project=True)
    timeline_ops.create_timeline(conn, name, width, height, fps)
    output(
        mutation_payload(
            action="timeline.create",
            target={"kind": "timeline", "name": name},
            width=width,
            height=height,
            fps=fps,
            message=f"Created timeline: {name}",
        )
    )


@app.command("switch")
@handle_errors
def switch_timeline(
    name: Optional[str] = typer.Argument(None, help="Timeline name"),
    index: Optional[int] = typer.Option(None, "--index", "-i", help="Timeline index"),
):
    """Switch to a different timeline."""
    if not name and index is None:
        raise ValidationError(
            "Provide a timeline name or --index.",
            details={"name": name, "index": index},
        )
    if name and index is not None:
        raise ValidationError(
            "Provide either a timeline name or --index, not both.",
            details={"name": name, "index": index},
            recoverability="not_applicable",
        )
    enforce_mutation_policy(
        "timeline.switch",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        target = f"index {index}" if index is not None else f"'{name}'"
        dry_run_message(f"Would switch to timeline {target}")
        return

    conn = get_connection(require_project=True)
    result = timeline_ops.switch_timeline(conn, name, index, return_details=True)
    output(
        mutation_payload(
            action="timeline.switch",
            changed=bool(result.get("changed")),
            target=result.get("target"),
            pre=result.get("pre"),
            final=result.get("final"),
            requested=result.get("requested"),
            api_result=result.get("api_result"),
            verified=result.get("verified"),
            message=f"Switched to timeline: {result.get('final', {}).get('name')}",
        )
    )


@app.command()
@handle_errors
def delete(
    name: str = typer.Argument(..., help="Timeline name"),
    force: bool = typer.Option(False, "--force", "-f"),
):
    """Delete a timeline."""
    enforce_mutation_policy(
        "timeline.delete",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would delete timeline: {name}")
        return
    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode mutation requires --force.",
                details={"action": "timeline.delete", "target_kind": "timeline", "target_name": name},
            )
        typer.confirm(f"Delete timeline '{name}'?", abort=True)

    conn = get_connection(require_project=True)
    timeline_ops.delete_timeline(conn, name)
    output(
        mutation_payload(
            action="timeline.delete",
            target={"kind": "timeline", "name": name},
            message=f"Deleted timeline: {name}",
        )
    )
