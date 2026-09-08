"""Independent native reference capture, before changing the original targets."""

from __future__ import annotations

import math
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from typing import Any

from ..errors import APICallFailed, ValidationError
from ..runtime_health import resolve_current_disk_project_db
from . import clip_speed_db, db_session, retime_render_proof, timeline_duplicate
from .retime_reference_donor import prepare_reference_donor, apply_reference_donors
from .retime_reference_workspace import ReferenceWorkspace
from .retime_reference_xml import requested_sources, reference_document
from .timeline_source_range import _source_total_frames, _source_fps as media_source_fps
from .retime_source_metadata import _comparison_rate
from .retime_playhead_diagnostics import reference_diagnostics


def capture_speed_ramp_reference(conn: Any, updates: list[dict[str, Any]]) -> dict[str, Any]:
    """Use an independent reference when the restored original lacks a sample."""
    with reference_diagnostics():
        try:
            return retime_render_proof.capture_retime_reference_frames(conn, updates)
        except APICallFailed as failure:
            if (failure.details.get("reason") != "retime_source_reference_unavailable"
                    or getattr(failure, "possible_mutation", "possible") != "none"):
                raise
        return capture_native_reference(conn, updates)


def _rows(path: str) -> dict[str, dict[str, Any]]:
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        return {row["Sm2TiItem_id"]: dict(row) for row in connection.execute("SELECT * FROM Sm2TiItem")}


def _save(conn: Any) -> None:
    if conn.project_manager.SaveProject() is not True:
        raise APICallFailed("Native reference preparation could not save the current project.")
    time.sleep(5.0)  # Same native save flush interval as the owning DB session.


def _video_items(timeline: Any) -> list[dict[str, Any]]:
    result = []
    for track in range(1, int(timeline.GetTrackCount("video") or 0) + 1):
        for item in timeline.GetItemListInTrack("video", track) or []:
            identity = item.GetUniqueId()
            if not isinstance(identity, str) or not identity:
                raise ValidationError("Reference capture requires exact native video identities.")
            result.append({"id": identity, "track": track, "start": int(item.GetStart()),
                           "duration": int(item.GetDuration()), "item": item})
    if len({row["id"] for row in result}) != len(result):
        raise ValidationError("Reference capture found duplicate native video identities.")
    return result


def _inputs(conn: Any, updates: list[dict[str, Any]], original_rows: dict[str, Any]) -> list[dict[str, Any]]:
    live = {row["id"]: row for row in _video_items(conn.timeline)}
    clips = []
    for update in updates:
        authoring = update.get("reference_authoring")
        item_id = str(update["item_id"])
        row, selected = original_rows.get(item_id), live.get(item_id)
        if not isinstance(authoring, dict) or row is None or selected is None:
            raise ValidationError("Independent reference capture requires exact pre-encoding authoring geometry.")
        if selected["start"] != update["start"] or selected["duration"] != update["old_duration"]:
            raise ValidationError("Reference target moved after speed-ramp planning.")
        if clip_speed_db._record_in_frames(row) != authoring["record_in"] or float(row.get("MediaStartTime") or 0) != 0:
            raise ValidationError("Reference capture cannot verify the current media-time origin.")
        media = selected["item"].GetMediaPoolItem()
        properties = media.GetClipProperty() if media is not None else None
        if not isinstance(properties, dict) or not properties.get("File Path"):
            raise ValidationError("Independent reference capture requires an identifiable source media file.")
        if not math.isclose(_comparison_rate(media_source_fps(properties, math.nan)),
                            _comparison_rate(authoring["source_fps"]), rel_tol=1e-9):
            raise ValidationError("Reference source media and native frame rates do not agree.")
        source_frames = _source_total_frames(properties, authoring["source_fps"])
        source_path = Path(properties["File Path"])
        if source_frames is None or not source_path.is_file():
            raise ValidationError("Independent reference capture could not establish the available source media.")
        if not math.isclose(clip_speed_db._source_fps(row, fallback_fps=math.nan), authoring["source_fps"], rel_tol=1e-12):
            raise ValidationError("Reference source frame rate changed after planning.")
        expected = requested_sources(authoring["points"], record_in=authoring["record_in"],
                                     record_fps=authoring["record_fps"], source_fps=authoring["source_fps"],
                                     duration=int(update["new_duration"]))
        clips.append({"source_path": source_path, "source_fps": authoring["source_fps"],
                      "source_frames": source_frames, "record_in": authoring["record_in"],
                      "start": update["start"], "duration": update["new_duration"],
                      "expected_sources": expected, "update": update, "track": selected["track"]})
    return sorted(clips, key=lambda row: row["start"])


def capture_native_reference(conn: Any, updates: list[dict[str, Any]]) -> dict[str, Any]:
    """Create/import a donor, capture a full-context copy, and clean native state.

    Original target rows are protected throughout; the owning command performs
    its actual mutation only after this reference and cleanup succeed.
    """
    video = [row for row in updates if row.get("media_kind") == "video"]
    if not video:
        raise ValidationError("Independent reference capture requires video targets.")
    directory = Path(tempfile.mkdtemp(prefix="cutagent-native-retime-reference-"))
    owner = None
    reference = None
    try:
        with retime_render_proof._still_export_page(conn):
            _save(conn)
            path = str(resolve_current_disk_project_db(conn, allow_project_name_inference=True)["project_db_path"])
            originals = _rows(path)
            clips = _inputs(conn, video, originals)
            rate = float(video[0]["reference_authoring"]["record_fps"])
            settings = conn.timeline.GetSetting()
            owner = ReferenceWorkspace(conn)
            document = reference_document(clips, name=owner.name, record_fps=rate,
                                          timeline_start=int(conn.timeline.GetStartFrame()),
                                          width=int(settings["timelineResolutionWidth"]),
                                          height=int(settings["timelineResolutionHeight"]))
            xml_path = directory / "reference.fcpxml"
            xml_path.write_bytes(document)
            try:
                owner.open()
                timeline_duplicate.duplicate_timeline(conn, owner.name + " copy", allow_drt=False)
                created = [row for row in timeline_duplicate._timeline_inventory(conn)
                           if row["identity"] not in owner.before_ids]
                if len(created) != 1:
                    raise APICallFailed("Reference duplication did not establish exactly one new timeline.")
                clone_id = owner.register_timeline(created[0]["timeline"])
                clone_items = _video_items(created[0]["timeline"])
                donor = conn.media_pool.ImportTimelineFromFile(str(xml_path), {
                    "timelineName": owner.name + " donor", "importSourceClips": False,
                    "sourceClipsFolders": [row["object"] for row in owner.before_pool["folders"].values()],
                })
                owner.register_timeline(donor)
                donor_items = _video_items(donor)
                pairs = []
                for clip in clips:
                    targets = [item for item in clone_items if item["track"] == clip["track"] and item["start"] == clip["start"] and item["duration"] == clip["duration"]]
                    donors = [item for item in donor_items if item["start"] == clip["start"] and item["duration"] == clip["duration"]]
                    if len(targets) != 1 or len(donors) != 1:
                        raise APICallFailed("Reference donor and copied target could not be identified exactly.")
                    pairs.append((clip, targets[0]["id"], donors[0]["id"]))
                owner.activate(clone_id)
                plans = []

                def writer(_connection, cursor, _session):
                    current = {row["Sm2TiItem_id"]: dict(row) for row in cursor.execute("SELECT * FROM Sm2TiItem")}
                    if any(current.get(key) != row for key, row in originals.items()):
                        raise APICallFailed("Reference preparation changed a pre-existing timeline item.")
                    for clip, target_id, donor_id in pairs:
                        plans.append(prepare_reference_donor(current[target_id], current[donor_id], record_fps=rate,
                                                             expected_source_frames=clip["expected_sources"], protected_item_ids=set(originals)))
                    return apply_reference_donors(cursor, plans)

                def verifier(fresh, _result, session):
                    nonlocal reference
                    owner.conn = fresh
                    owner.activate(clone_id)
                    current = _rows(session.project_db_path)
                    if any(current.get(key) != row for key, row in originals.items()):
                        raise APICallFailed("Reference rendering changed a pre-existing timeline item.")
                    samples = []
                    for index, ((clip, target_id, _donor_id), plan) in enumerate(zip(pairs, plans, strict=True)):
                        if current[target_id] != {**plan["before_row"], "MediaTimemapBA": plan["native_timemap"]}:
                            raise APICallFailed("Native reference reopen did not preserve the copied target's properties.")
                        update = clip["update"]
                        for sample_index, frame in enumerate(retime_render_proof._sample_after_frames(update)):
                            capture = retime_render_proof._export(fresh, directory, f"native-{index}-{sample_index}", frame)
                            samples.append({"item_id": str(update["item_id"]), "before_record_frame": frame,
                                            "after_record_frame": frame, "expected_source_frame": clip["expected_sources"][frame-clip["start"]],
                                            "before": capture, "frozen": bool(update["after_state"].get("frozen")),
                                            "reversed": bool(update["after_state"].get("reversed"))})
                    reference = {"directory": directory, "samples": samples, "reference_kind": "independent_native_import"}
                    return {"status": "verified", "reference_frames_rendered": len(samples)}

                db_session.execute_sqlite_disk_db_mutation(conn, context="Native retime reference copy", writer=writer, verifier=verifier)
            finally:
                conn.refresh()
                owner.cleanup(conn)
                _save(conn)
                current = _rows(path)
                if set(current) != set(originals) or any(current.get(key) != row for key, row in originals.items()):
                    raise APICallFailed("Reference cleanup did not restore the original project item inventory and state.")
        if not reference:
            raise APICallFailed("Independent native reference capture returned no rendered samples.")
        return reference
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
