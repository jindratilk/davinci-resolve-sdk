"""Target Media Pool sources nested inside native multicam angles."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid
from typing import Any

from ..errors import APICallFailed, ValidationError
from . import color_ops, color_source_grade, media_pool, native_multicam_db
from ._podcast_multicam import project_lifecycle


def _find_media_pool_source(conn: Any, source: dict[str, Any]) -> dict[str, Any]:
    matches = media_pool.collect_append_media_matches(conn)
    unique_id = str(source.get("media_pool_unique_id") or "").strip()
    media_id = str(source.get("media_id") or "").strip()
    source_path = str(source.get("source_path") or "").strip()
    clip_name = str(source.get("clip_name") or "").strip()
    exact: list[dict[str, Any]] = []
    for match in matches:
        clip = match.get("clip")
        candidate_ids: set[str] = set()
        for method_name in ("GetUniqueId", "GetMediaId"):
            getter = getattr(clip, method_name, None)
            if callable(getter):
                try:
                    value = getter()
                except Exception:
                    value = None
                if value:
                    candidate_ids.add(str(value))
        if unique_id and unique_id in candidate_ids:
            exact.append(match)
            continue
        if media_id and media_id in candidate_ids:
            exact.append(match)
    if not exact and source_path:
        exact = [match for match in matches if media_pool._source_path_matches(match.get("source_path"), source_path)]
    if not exact and clip_name:
        exact = [match for match in matches if str(match.get("name") or "") == clip_name]
    if len(exact) != 1:
        raise ValidationError(
            "The matched multicam source could not be resolved uniquely in the Media Pool.",
            details={
                "reason": "multicam_source_media_pool_match_not_unique",
                "source": source,
                "match_count": len(exact),
                "matches": [
                    {
                        "name": match.get("name"),
                        "folder": match.get("folder"),
                        "media_id": match.get("media_id"),
                        "source_path": match.get("source_path"),
                    }
                    for match in exact
                ],
            },
        )
    return exact[0]


def resolve_angle_source(
    conn: Any,
    *,
    project_db_path: str,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    angle_number: int,
    record_frame: int,
    media_type: str = "video",
) -> dict[str, Any]:
    match = native_multicam_db.match_multicam_frame(
        project_db_path,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        angle_number=angle_number,
        record_frame=record_frame,
        media_type=media_type,
    )
    if match.get("status") != "matched" or not isinstance(match.get("source"), dict):
        raise ValidationError(
            "The selected multicam angle/frame is an intentional gap and has no source to edit.",
            details={"reason": "multicam_source_gap", "match": match},
        )
    expected_source_native_id = os.environ.get("CUTAGENT_SDK_EXPECTED_MULTICAM_SOURCE_NATIVE_ID", "").strip()
    expected_item_index = os.environ.get("CUTAGENT_SDK_EXPECTED_MULTICAM_SOURCE_ITEM_INDEX", "").strip()
    matched_source = match["source"]
    if (expected_source_native_id and str(matched_source.get("media_id") or "") != expected_source_native_id) or (
        expected_item_index and int(matched_source.get("item_index", -1)) != int(expected_item_index)
    ):
        from ..errors import SdkMutationStaleRevision

        raise SdkMutationStaleRevision(
            "The exact SDK multicam source identity changed before execution.",
            details={"reason": "sdk_multicam_source_guard_mismatch"},
        )
    media_match = _find_media_pool_source(conn, match["source"])
    return {
        "match": match,
        "media_pool": {
            "name": media_match.get("name"),
            "folder": media_match.get("folder"),
            "media_id": media_match.get("media_id"),
            "source_path": media_match.get("source_path"),
        },
        "clip": media_match["clip"],
    }


def set_angle_source_property(
    conn: Any,
    *,
    project_db_path: str,
    key: str,
    value: str,
    **target: Any,
) -> dict[str, Any]:
    normalized_key = str(key or "").strip()
    if not normalized_key:
        raise ValidationError("Multicam angle source property key cannot be empty.")
    resolved = resolve_angle_source(conn, project_db_path=project_db_path, **target)
    clip = resolved.pop("clip")
    setter = getattr(clip, "SetClipProperty", None)
    getter = getattr(clip, "GetClipProperty", None)
    if not callable(setter) or not callable(getter):
        raise APICallFailed(
            "The matched Media Pool source does not expose clip property read/write APIs.",
            details={"required_methods": ["MediaPoolItem.SetClipProperty", "MediaPoolItem.GetClipProperty"]},
        )
    try:
        before = getter(normalized_key)
        setter_result = setter(normalized_key, value)
        after = getter(normalized_key)
    except Exception as exc:
        raise APICallFailed(
            "Failed to set a property on the matched multicam angle source.",
            details={"key": normalized_key, "value": value, "error": str(exc)},
        ) from exc
    if str(after) != str(value):
        raise APICallFailed(
            "DaVinci Resolve did not retain the requested multicam angle source property.",
            details={"key": normalized_key, "expected": value, "actual": after, "setter_result": setter_result},
        )
    return {
        "action": "multicam.source.property_set",
        "changed": str(before) != str(after),
        "key": normalized_key,
        "requested_value": value,
        "before": before,
        "after": after,
        "route": "multicam.match_frame -> MediaPoolItem.SetClipProperty/GetClipProperty",
        "verification": {"status": "verified", "actual": after, "expected": value},
        **resolved,
    }


def _merge_json_object(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_json_object(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _json_patch_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _json_patch_matches(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, float) and isinstance(actual, (int, float)):
        return abs(float(actual) - expected) <= 1e-6
    return actual == expected


def _parse_cdl_values(value: Any) -> tuple[float, ...] | None:
    if isinstance(value, (int, float)):
        return (float(value),)
    if isinstance(value, str):
        parts = [part for part in value.replace(",", " ").split() if part]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        return None
    try:
        return tuple(float(part) for part in parts)
    except (TypeError, ValueError):
        return None


def _cdl_readback_matches(requested: dict[str, Any], readback: Any) -> tuple[bool, dict[str, Any]]:
    """Compare requested CDL values with an independently returned node-1 readback."""

    if not isinstance(readback, dict) or readback.get("available") is False:
        return False, {}
    actual = readback.get("cdl") if isinstance(readback.get("cdl"), dict) else readback
    if not isinstance(actual, dict):
        return False, {}
    normalized_actual: dict[str, Any] = {}
    for key in ("Slope", "Offset", "Power", "Saturation"):
        if key not in requested:
            continue
        expected_values = _parse_cdl_values(requested[key])
        actual_values = _parse_cdl_values(actual.get(key))
        normalized_actual[key] = actual.get(key)
        if expected_values is None or actual_values is None or len(expected_values) != len(actual_values):
            return False, normalized_actual
        if any(abs(expected - observed) > 1e-5 for expected, observed in zip(expected_values, actual_values)):
            return False, normalized_actual
    return True, normalized_actual


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.cutagent-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def _find_timeline_by_name(project: Any, name: str | None) -> Any | None:
    if not name:
        return None
    for index in range(1, int(project.GetTimelineCount() or 0) + 1):
        timeline = project.GetTimelineByIndex(index)
        if timeline and str(timeline.GetName() or "") == name:
            return timeline
    return None


def apply_angle_source_braw_sidecar(
    conn: Any,
    *,
    project_db_path: str,
    raw_settings: dict[str, Any],
    **target: Any,
) -> dict[str, Any]:
    """Patch and prove BRAW processing settings on an exact multicam source.

    Blackmagic Design documents BRAW sidecars as editable JSON and exposes
    TimelineItem.UpdateSidecar() for DaVinci Resolve read/write integration.
    Re-serializing the sidecar through that API after a project reopen proves
    that the BRAW SDK accepted the requested values, rather than merely proving
    that bytes were written next to the source file.
    """

    if not isinstance(raw_settings, dict) or not raw_settings:
        raise ValidationError("BRAW source settings must be a non-empty JSON object.")
    resolved = resolve_angle_source(conn, project_db_path=project_db_path, **target)
    clip = resolved.pop("clip")
    source_path = Path(str(resolved["media_pool"].get("source_path") or "")).expanduser().resolve()
    if source_path.suffix.casefold() != ".braw":
        raise ValidationError(
            "The matched multicam source is not a Blackmagic RAW .braw clip.",
            details={"source_path": str(source_path), "required_extension": ".braw"},
        )
    if not source_path.is_file():
        raise ValidationError("The matched BRAW source file does not exist.", details={"source_path": str(source_path)})

    properties = media_pool._clip_properties(clip)
    source_timecode = str(properties.get("Start TC") or properties.get("Start Timecode") or "00:00:00:00").strip()
    normalized_patch = dict(raw_settings)
    for key in ("exposure", "iso", "white_balance_kelvin", "white_balance_tint"):
        value = normalized_patch.get(key)
        if value is not None and not isinstance(value, dict):
            normalized_patch[key] = {source_timecode: value}

    sidecar_path = source_path.with_suffix(".sidecar")
    before_exists = sidecar_path.exists()
    before_bytes = sidecar_path.read_bytes() if before_exists else None
    try:
        before_payload = json.loads(before_bytes.decode("utf-8")) if before_bytes is not None else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(
            "The existing BRAW sidecar is not readable JSON; it was not modified.",
            details={"sidecar_path": str(sidecar_path), "error": str(exc)},
        ) from exc
    if not isinstance(before_payload, dict):
        raise ValidationError("The existing BRAW sidecar root must be a JSON object.", details={"sidecar_path": str(sidecar_path)})

    backup_path: Path | None = None
    if before_exists:
        backup_path = sidecar_path.with_name(f"{sidecar_path.name}.cutagent-{uuid.uuid4().hex[:12]}.bak")
        shutil.copy2(sidecar_path, backup_path)
    requested_payload = _merge_json_object(before_payload, normalized_patch)
    project_name = str(conn.project.GetName() or "").strip()
    original_timeline_name = str(conn.timeline.GetName() or "").strip() if conn.timeline is not None else None
    if not project_name:
        raise APICallFailed("A current project is required for BRAW sidecar verification.")

    steps: list[dict[str, Any]] = []
    temporary_timeline = None
    temporary_name: str | None = None
    try:
        _atomic_write_json(sidecar_path, requested_payload)
        steps.append({"name": "atomic_sidecar_write", "ok": True, "sidecar_path": str(sidecar_path)})
        steps.extend(project_lifecycle._save_and_close_current_project(conn, project_name=project_name))
        steps.append(project_lifecycle._reopen_project(conn, project_name=project_name))

        reopened_project = conn.project
        reopened_original = _find_timeline_by_name(reopened_project, original_timeline_name)
        reopened = resolve_angle_source(conn, project_db_path=project_db_path, **target)
        reopened_clip = reopened.pop("clip")
        temporary_name = f"__CutAgent BRAW Sidecar Proof {uuid.uuid4().hex[:12]}"
        temporary_timeline = conn.media_pool.CreateTimelineFromClips(temporary_name, [reopened_clip])
        if not temporary_timeline or not reopened_project.SetCurrentTimeline(temporary_timeline):
            raise APICallFailed(
                "DaVinci Resolve did not create the temporary BRAW sidecar proof timeline.",
                details={"timeline_name": temporary_name},
            )
        conn.refresh()
        items = list(conn.timeline.GetItemListInTrack("video", 1) or [])
        if len(items) != 1 or not callable(getattr(items[0], "UpdateSidecar", None)):
            raise APICallFailed(
                "The matched BRAW source does not expose TimelineItem.UpdateSidecar().",
                details={"timeline_name": temporary_name, "video_item_count": len(items)},
            )
        if items[0].UpdateSidecar() is False:
            raise APICallFailed("DaVinci Resolve rejected the BRAW sidecar through TimelineItem.UpdateSidecar().")
        steps.append({"name": "resolve_api_update_sidecar", "ok": True})
        if conn.project_manager.SaveProject() is False:
            raise APICallFailed("DaVinci Resolve did not save the project after BRAW sidecar verification.")
        canonical_payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        accepted = _json_patch_matches(canonical_payload, normalized_patch)
        if not accepted:
            raise APICallFailed(
                "DaVinci Resolve did not retain the requested BRAW processing settings.",
                details={
                    "requested_patch": normalized_patch,
                    "canonical_sidecar": canonical_payload,
                    "sidecar_path": str(sidecar_path),
                },
            )
        if reopened_original is not None:
            reopened_project.SetCurrentTimeline(reopened_original)
        if conn.media_pool.DeleteTimelines([temporary_timeline]) is False:
            raise APICallFailed("The BRAW sidecar proof succeeded but its temporary timeline was not deleted.")
        temporary_timeline = None
        conn.refresh()
        return {
            "action": "multicam.source.raw_braw_set",
            "changed": requested_payload != before_payload,
            "raw_format": "Blackmagic RAW",
            "requested_patch": normalized_patch,
            "canonical_sidecar": canonical_payload,
            "sidecar_path": str(sidecar_path),
            "backup_path": str(backup_path) if backup_path is not None else None,
            "source_timecode": source_timecode,
            "route": "multicam.match_frame -> atomic BRAW JSON sidecar -> save/close/reopen -> TimelineItem.UpdateSidecar readback",
            "steps": steps,
            "verification": {
                "status": "verified",
                "sidecar_json_readback": True,
                "davinci_resolve_api_reserialized": True,
                "requested_patch_retained": True,
            },
            **resolved,
        }
    except Exception as operation_error:
        rollback_steps: list[dict[str, Any]] = []
        rollback_errors: list[str] = []
        try:
            current_project = getattr(conn, "project", None)
            if current_project is not None and str(current_project.GetName() or "") == project_name:
                rollback_steps.extend(project_lifecycle._save_and_close_current_project(conn, project_name=project_name))
        except Exception as rollback_error:
            rollback_errors.append(f"close_modified_project:{rollback_error}")
        try:
            if before_exists:
                if backup_path is None or not backup_path.is_file():
                    raise OSError("The exact pre-mutation BRAW sidecar backup is unavailable.")
                shutil.copy2(backup_path, sidecar_path)
            elif sidecar_path.exists():
                sidecar_path.unlink()
            restored_bytes = sidecar_path.read_bytes() if sidecar_path.exists() else None
            if restored_bytes != before_bytes:
                raise OSError("The BRAW sidecar bytes do not match the exact pre-mutation state.")
            rollback_steps.append({"name": "restore_exact_sidecar", "ok": True, "exists": before_exists})
        except Exception as rollback_error:
            rollback_errors.append(f"restore_sidecar:{rollback_error}")
        try:
            rollback_steps.append(project_lifecycle._reopen_project(conn, project_name=project_name))
            reopened_project = conn.project
            if temporary_name:
                reopened_temporary = _find_timeline_by_name(reopened_project, temporary_name)
                if reopened_temporary is not None:
                    if conn.media_pool.DeleteTimelines([reopened_temporary]) is False:
                        raise APICallFailed("DaVinci Resolve refused to delete the temporary BRAW proof timeline during rollback.")
                    rollback_steps.append({"name": "delete_temporary_timeline", "ok": True, "timeline_name": temporary_name})
            original = _find_timeline_by_name(reopened_project, original_timeline_name)
            if original_timeline_name and original is None:
                raise APICallFailed(
                    "The original timeline could not be restored after BRAW sidecar rollback.",
                    details={"timeline_name": original_timeline_name},
                )
            if original is not None and reopened_project.SetCurrentTimeline(original) is False:
                raise APICallFailed(
                    "DaVinci Resolve refused to restore the original timeline after BRAW sidecar rollback.",
                    details={"timeline_name": original_timeline_name},
                )
            conn.refresh()
            restored_bytes = sidecar_path.read_bytes() if sidecar_path.exists() else None
            if restored_bytes != before_bytes:
                raise APICallFailed(
                    "DaVinci Resolve did not retain the restored BRAW sidecar after project reopen.",
                    details={"sidecar_path": str(sidecar_path), "expected_exists": before_exists},
                )
            rollback_steps.append({"name": "reopen_and_verify_restored_sidecar", "ok": True})
        except Exception as rollback_error:
            rollback_errors.append(f"reopen_and_verify:{rollback_error}")
        if rollback_errors:
            raise APICallFailed(
                "The BRAW source-setting operation failed and its rollback could not be fully verified.",
                details={
                    "operation_error": str(operation_error),
                    "rollback_errors": rollback_errors,
                    "rollback_steps": rollback_steps,
                    "sidecar_path": str(sidecar_path),
                },
                recoverability="manual",
            ) from operation_error
        raise APICallFailed(
            "DaVinci Resolve rejected the BRAW source-setting operation; the exact prior sidecar state was restored and verified.",
            details={
                "operation_error": str(operation_error),
                "rollback_status": "verified",
                "rollback_steps": rollback_steps,
                "sidecar_path": str(sidecar_path),
            },
        ) from operation_error


def apply_angle_source_cdl(
    conn: Any,
    *,
    project_db_path: str,
    version_name: str,
    node: int = 1,
    slope: str | None = None,
    offset: str | None = None,
    power: str | None = None,
    saturation: float | None = None,
    **target: Any,
) -> dict[str, Any]:
    normalized_version_name = str(version_name or "").strip()
    if not normalized_version_name:
        raise ValidationError("Multicam source-grade version name cannot be empty.")
    node_index, cdl_requested = color_ops.validate_cdl_payload(
        node,
        slope=slope,
        offset=offset,
        power=power,
        saturation=saturation,
    )
    if node_index != 1:
        raise ValidationError(
            "Multicam source-grade CDL currently supports node 1 only because DaVinci Resolve does not expose reliable node-scoped CDL readback for higher nodes.",
            details={"node": node_index, "supported_nodes": [1]},
        )
    if len(cdl_requested) == 1:
        raise ValidationError("Multicam source-grade requires at least one CDL value.")
    resolved = resolve_angle_source(conn, project_db_path=project_db_path, **target)
    clip = resolved.pop("clip")
    project = getattr(conn, "project", None)
    media_pool_api = getattr(conn, "media_pool", None)
    resolve = getattr(conn, "resolve", None)
    if project is None or media_pool_api is None:
        raise APICallFailed("A current project and Media Pool are required for multicam source grading.")
    original_timeline = getattr(conn, "timeline", None)
    original_page = None
    get_page = getattr(resolve, "GetCurrentPage", None)
    if callable(get_page):
        try:
            original_page = get_page()
        except Exception:
            original_page = None
    temporary_name = f"__CutAgent Multicam Source Grade {uuid.uuid4().hex[:12]}"
    temporary_timeline = None
    cleanup: dict[str, Any] = {"temporary_timeline_name": temporary_name, "deleted": False, "restored_timeline": False}
    operation_error: Exception | None = None
    try:
        temporary_timeline = media_pool_api.CreateTimelineFromClips(temporary_name, [clip, clip])
        if not temporary_timeline:
            raise APICallFailed(
                "DaVinci Resolve did not create the temporary source-grade proof timeline.",
                details={"timeline_name": temporary_name},
            )
        if not project.SetCurrentTimeline(temporary_timeline):
            raise APICallFailed("DaVinci Resolve did not activate the temporary source-grade timeline.")
        conn.refresh()
        open_page = getattr(resolve, "OpenPage", None)
        if callable(open_page) and not open_page("color"):
            raise APICallFailed("DaVinci Resolve did not open the Color page through its scripting API.")
        clip_name = str(resolved["media_pool"].get("name") or "")
        prepared = color_source_grade.prepare_remote_source_grade(
            conn,
            name=normalized_version_name,
            clip_name=clip_name,
            create=True,
            load=True,
            include_singletons=True,
        )
        prepared_status = (prepared.get("verification") or {}).get("status")
        if prepared_status != "verified":
            raise APICallFailed(
                "The multicam source-grade remote scope could not be verified before mutation.",
                details={"prepare_remote": prepared, "required_status": "verified"},
            )
        applied = color_ops.set_cdl(
            conn,
            clip_name,
            node_index,
            slope=slope,
            offset=offset,
            power=power,
            saturation=saturation,
        )
        save = getattr(conn.project_manager, "SaveProject", None)
        if callable(save) and save() is False:
            raise APICallFailed("DaVinci Resolve did not save the multicam source grade.")
        readback = color_ops.get_cdl(conn, clip_name, node_index=node_index)
        readback_matches, canonical_readback = _cdl_readback_matches(cdl_requested, readback)
        if not bool(applied) or not readback_matches:
            raise APICallFailed(
                "DaVinci Resolve did not retain the requested multicam source CDL values.",
                details={
                    "setter_result": applied,
                    "requested": cdl_requested,
                    "readback": readback,
                    "canonical_readback": canonical_readback,
                },
            )
        return {
            "action": "multicam.source_grade.apply_cdl",
            "changed": bool(applied),
            "version_name": normalized_version_name,
            "node": node_index,
            "cdl_requested": cdl_requested,
            "prepare_remote": prepared,
            "readback": readback,
            "route": "multicam.match_frame -> temporary API timeline -> remote source grade -> TimelineItem.SetCDL",
            "cleanup": cleanup,
            "verification": {
                "status": "verified",
                "remote_scope": prepared_status,
                "cdl_readback": readback,
                "requested_values_match_readback": True,
            },
            **resolved,
        }
    except Exception as exc:
        operation_error = exc
        raise
    finally:
        cleanup_errors: list[str] = []
        try:
            if original_timeline is not None:
                cleanup["restored_timeline"] = bool(project.SetCurrentTimeline(original_timeline))
                if not cleanup["restored_timeline"]:
                    cleanup_errors.append("restore_timeline:DaVinci Resolve returned false")
            elif temporary_timeline is not None:
                cleanup["restored_timeline"] = True
        except Exception as exc:
            cleanup_errors.append(f"restore_timeline:{exc}")
        if temporary_timeline is not None:
            try:
                cleanup["deleted"] = bool(media_pool_api.DeleteTimelines([temporary_timeline]))
                if not cleanup["deleted"]:
                    cleanup_errors.append("delete_temporary_timeline:DaVinci Resolve returned false")
            except Exception as exc:
                cleanup_errors.append(f"delete_temporary_timeline:{exc}")
        if callable(getattr(resolve, "OpenPage", None)) and original_page:
            try:
                resolve.OpenPage(original_page)
            except Exception as exc:
                cleanup_errors.append(f"restore_page:{exc}")
        try:
            conn.refresh()
        except Exception as exc:
            cleanup_errors.append(f"refresh:{exc}")
        cleanup["errors"] = cleanup_errors
        if cleanup_errors and operation_error is None:
            raise APICallFailed(
                "Multicam source grade was applied but temporary workflow cleanup failed.",
                details=cleanup,
            )
