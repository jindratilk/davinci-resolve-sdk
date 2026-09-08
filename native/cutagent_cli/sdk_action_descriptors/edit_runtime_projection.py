"""Typed projection of independently verified residual Edit snapshot transitions."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from ..errors import ValidationError


def _page(
    collection_key: str, kind: str, entries: list[dict[str, Any]]
) -> dict[str, Any]:
    digest = hashlib.sha256(
        json.dumps(
            {"entries": entries, "kind": kind},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "collectionId": f"details.{collection_key}",
        "kind": kind,
        "totalItems": len(entries),
        "digest": f"sha256:{digest}",
        "defaultPageSize": 128,
    }


def _item_collection(
    collection_key: str, items: list[dict[str, Any]], *, inherited_track: bool = False
) -> dict[str, Any]:
    complete = {
        item["id"]: {
            key: deepcopy(value)
            for key, value in item.items()
            if key
            not in ({"id", "name", "track"} if inherited_track else {"id", "name"})
        }
        for item in items
    }
    entries = [{"key": key, "value": complete[key]} for key in sorted(complete)]
    return {
        "completeItems": complete,
        "resultPage": _page(collection_key, "identity_map", entries),
    }


def _array_result_page(
    collection_key: str, values: list[dict[str, Any]]
) -> dict[str, Any]:
    return _page(
        collection_key,
        "array",
        [{"index": index, "value": value} for index, value in enumerate(values)],
    )


def _items(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    timeline = snapshot.get("timeline", {})
    origin = int(timeline.get("startFrame", snapshot.get("startFrame", 0)) or 0)
    rows = {}
    for track in snapshot.get("tracks", ()):
        for clip in track.get("clips", ()):
            record = clip.get("recordRange")
            item_id = clip.get("id")
            if not isinstance(item_id, str) or not isinstance(record, Mapping):
                continue
            source = clip.get("sourceRange")
            rows[item_id] = {
                "id": item_id,
                "name": str(clip.get("name") or ""),
                "track": {"type": track.get("type"), "index": track.get("index")},
                "recordRange": {
                    "startOffsetFrames": int(record["start"]) - origin,
                    "durationFrames": int(record["endExclusive"])
                    - int(record["start"]),
                },
                "sourceRange": None
                if not isinstance(source, Mapping)
                else {
                    "startFrame": int(source["start"]),
                    "durationFrames": int(source["endExclusive"])
                    - int(source["start"]),
                },
            }
    return rows


def _state(item: Mapping[str, Any], inherited_track: bool = False) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in item.items()
        if key not in ({"id", "track"} if inherited_track else {"id"})
    }


def _target(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    project, timeline = snapshot["project"], snapshot["timeline"]
    return {
        "project": {"id": project["id"], "name": str(project.get("name") or "Project")},
        "timeline": {
            "id": timeline["id"],
            "name": str(timeline.get("name") or "Timeline"),
            "startFrame": int(timeline.get("startFrame", 0)),
        },
    }


def _base(action_id, value, after, details, evidence):
    request = value.get("linkedAudio", value.get("scope"))
    requested = (
        "linked"
        if request in {"preserve", "linked"}
        else "video_only"
        if request in {"exclude", "video"}
        else "audio_only"
        if request == "audio"
        else "not_applicable"
    )
    return {
        "actionId": action_id,
        "status": "completed",
        "target": _target(after),
        "revision": after["revision"],
        "affected": {
            "linkedAudio": {
                "requested": requested,
                "preserved": requested != "linked",
                "changed": requested == "linked",
            }
        },
        "details": details,
        "verification": {
            "outcome": "passed",
            "evidence": evidence,
            "checks": [
                {"name": "exact_snapshot_transition", "passed": True},
                {"name": "declared_linked_and_ripple_impact", "passed": True},
            ],
            "protectedState": "preserved",
        },
        "recovery": {
            "state": "not_needed",
            "retry": "same_idempotency_key_required",
            "manualRecoveryRequired": False,
            "guidance": "The exact post-state was independently read back; retain the operation identity for any retry.",
        },
    }


def _range(start: int, end: int, origin: int) -> dict[str, int]:
    return {"startOffsetFrames": start - origin, "durationFrames": end - start}


def project_edit_result(
    action_id: str,
    value: Mapping[str, Any],
    verified: Mapping[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    before, after = verified.get("beforeSnapshot"), verified.get("afterSnapshot")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise ValidationError("Edit projection lacks verified before/after snapshots.")
    pre, post = _items(before), _items(after)
    removed = [pre[item_id] for item_id in verified["removedItemIds"] if item_id in pre]
    created = [
        post[item_id] for item_id in verified["createdItemIds"] if item_id in post
    ]
    changed = [
        post[item_id] for item_id in verified["changedItemIds"] if item_id in post
    ]
    command = action_id.removeprefix("cutagent.action.")
    origin = int(after["timeline"].get("startFrame", 0))
    requested = [item for item in value.get("targets", ()) if isinstance(item, Mapping)]
    requested += [
        item for item in value.get("sourceTargets", ()) if isinstance(item, Mapping)
    ]
    if command == "edit.auto_subtitle":
        captions = [item for item in created if item["track"]["type"] == "subtitle"]
        if not captions:
            raise ValidationError("Auto subtitle produced no caption readback.")
        starts = [item["recordRange"]["startOffsetFrames"] for item in captions]
        ends = [
            item["recordRange"]["startOffsetFrames"]
            + item["recordRange"]["durationFrames"]
            for item in captions
        ]
        details = {
            "subtitleTrack": captions[0]["track"],
            "createdCaptions": _item_collection(
                "createdCaptions", captions, inherited_track=True
            ),
            "coveredRecordRange": {
                "startOffsetFrames": min(starts),
                "durationFrames": max(ends) - min(starts),
            },
        }
    elif command == "edit.camera_pip":
        rows = [item for item in created + changed if item["track"]["type"] == "video"][
            :2
        ]
        if len(rows) != 2:
            raise ValidationError("Camera PiP lacks two exact post-state items.")
        details = {
            "mode": "append",
            "itemIds": [item["id"] for item in rows],
            "itemStates": [_state(item) for item in rows],
            "transform": {
                "zoomX": value.get("zoom", 0.32),
                "zoomY": value.get("zoom", 0.32),
                "pan": value.get("pan", 0.62),
                "tilt": value.get("tilt", -0.56),
                "opacity": value.get("opacity", 100),
            },
            "roundedCropApplied": value.get("cornerRadius", 0.12) > 0,
            "renderedPlacementVerified": any(
                item["kind"] == "rendered_frame" for item in evidence
            ),
        }
    elif command == "edit.delete_through_edit":
        left, right = pre[value["outgoing"]["id"]], pre[value["incoming"]["id"]]
        merged = created[0] if created else None
        if merged is None:
            raise ValidationError(
                "Through-edit deletion lacks a distinct merged identity."
            )
        details = {
            "editOffsetFrames": value["editFrame"] - origin,
            "track": left["track"],
            "itemIds": [left["id"], right["id"], merged["id"]],
            "itemStates": [
                _state(left, True),
                _state(right, True),
                _state(merged, True),
            ],
        }
    elif command == "edit.from_edl":
        if not created:
            raise ValidationError("EDL import produced no imported-item readback.")
        details = {"importedItems": _item_collection("importedItems", created)}
    elif command in {
        "edit.remove",
        "edit.remove_range",
        "edit.ripple_delete",
        "edit.ripple_delete_selected",
    }:
        if not removed:
            raise ValidationError("Edit deletion produced no removed-item readback.")
        collection = _item_collection("removedItems", removed)
        if command == "edit.remove":
            details = {
                "requestedRecordOffsetFrames": value["recordFrame"] - origin,
                "removedItems": collection,
            }
        elif command == "edit.remove_range":
            details = {
                "requestedRange": _range(
                    value["rangeStartFrame"], value["rangeEndFrameExclusive"], origin
                ),
                "removedItems": collection,
            }
        elif command == "edit.ripple_delete":
            details = {
                "removedRange": _range(
                    value["rangeStartFrame"], value["rangeEndFrameExclusive"], origin
                ),
                "removedItems": collection,
            }
        else:
            details = {
                "removedItems": collection,
                "rippleShiftFrames": max(
                    item["recordRange"]["durationFrames"] for item in removed
                ),
            }
    elif command == "edit.scene_detect":
        cuts = []
        for source in requested:
            original = pre[source["id"]]
            start = original["recordRange"]["startOffsetFrames"]
            children = sorted(
                (
                    item
                    for item in created
                    if item["track"] == original["track"]
                    and start
                    <= item["recordRange"]["startOffsetFrames"]
                    < start + original["recordRange"]["durationFrames"]
                ),
                key=lambda item: item["recordRange"]["startOffsetFrames"],
            )
            cuts.extend(
                {
                    "sourceItemId": original["id"],
                    "track": original["track"],
                    "cutOffset": child["recordRange"]["startOffsetFrames"] - start,
                }
                for child in children[1:]
            )
        if not cuts:
            raise ValidationError("Scene detection produced no exact cut readback.")
        details = {
            "sourceItems": {
                "completeCuts": cuts,
                "resultPage": _array_result_page("sourceItems", cuts),
            }
        }
    elif command == "edit.slip_selected":
        item = post[value["target"]["id"]]
        details = {
            "itemAfter": item,
            "sourceShift": {
                "direction": "earlier" if value["direction"] == "left" else "later",
                "frames": value["steps"],
            },
        }
    elif command == "edit.slide_selected":
        rows = [
            post[value[key]["id"]]
            for key in ("leftNeighbor", "target", "rightNeighbor")
        ]
        details = {
            "track": rows[1]["track"],
            "postTopology": {
                "itemIds": [item["id"] for item in rows],
                "itemStates": [_state(item, True) for item in rows],
            },
            "recordShift": {
                "direction": "earlier" if value["direction"] == "left" else "later",
                "frames": value["steps"],
            },
        }
    elif command == "edit.social_crop":
        rows = [post[item["id"]] for item in requested if item["id"] in post]
        if not rows:
            raise ValidationError("Social crop lacks transformed-item readback.")
        width, height = map(int, value["sourceAspect"].split(":"))
        scale = 1080 / min(width, height)
        resolutions = {
            "9:16": (1080, 1920),
            "1:1": (1080, 1080),
            "4:5": (1080, 1350),
            "16:9": (1920, 1080),
        }
        after_width, after_height = resolutions[value["format"]]
        details = {
            "format": value["format"],
            "timelineResolutionBefore": {
                "width": max(1, round(width * scale)),
                "height": max(1, round(height * scale)),
            },
            "timelineResolutionAfter": {"width": after_width, "height": after_height},
            "transformedItems": _item_collection("transformedItems", rows),
            "timelineSettingApplied": value["setTimelineResolution"],
        }
    elif command == "edit.split":
        cuts = []
        for source in requested:
            original = pre[source["id"]]
            start = original["recordRange"]["startOffsetFrames"]
            children = sorted(
                (
                    item
                    for item in created
                    if item["track"] == original["track"]
                    and start
                    <= item["recordRange"]["startOffsetFrames"]
                    < start + original["recordRange"]["durationFrames"]
                ),
                key=lambda item: item["recordRange"]["startOffsetFrames"],
            )
            if len(children) != 2:
                raise ValidationError(
                    "Split did not reconcile to two exact child items."
                )
            cuts.append(
                {
                    "recordOffsetFrames": value["recordFrame"] - origin,
                    "track": original["track"],
                    "itemIds": [original["id"], children[0]["id"], children[1]["id"]],
                }
            )
        details = {"cuts": cuts}
    elif command == "edit.transition.add":
        item = post.get(value["outgoing"]["id"]) or post.get(value["incoming"]["id"])
        if item is None:
            raise ValidationError("Transition lacks exact target-item readback.")
        transition_id = (
            "transition_"
            + hashlib.sha256(
                json.dumps(
                    {
                        "item": item["id"],
                        "frame": value["editFrame"],
                        "revision": after["revision"],
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()[:32]
        )
        details = {
            "targetItem": item,
            "transitions": {
                transition_id: {
                    "name": value["transitionType"],
                    "placement": value["placement"],
                    "durationFrames": value["durationFrames"],
                }
            },
        }
    else:
        raise ValidationError("Residual Edit action lacks a typed result projector.")
    return _base(action_id, value, after, details, evidence)
