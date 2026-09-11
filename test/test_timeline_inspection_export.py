from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutagent_cli.core import timeline_inspection_export
from cutagent_cli.errors import ValidationError


class _Group:
    def GetName(self):
        return "Hero grade"


class _Comp:
    def GetAttrs(self):
        return {"COMPS_Name": "Main comp"}

    def GetToolList(self, _selected):
        return {}


class _Media:
    def GetMediaId(self):
        return "media-1"

    def GetUniqueId(self):
        return "media-unique-1"

    def GetName(self):
        return "Source.mov"

    def GetClipProperty(self):
        return {"Type": "Video", "File Path": "/private/source.mov", "FPS": "24"}


class _Item:
    def GetUniqueId(self):
        return "item-1"

    def GetName(self):
        return "Hero"

    def GetStart(self):
        return 100

    def GetEnd(self):
        return 148

    def GetDuration(self):
        return 48

    def GetLeftOffset(self):
        return 12

    def GetRightOffset(self):
        return 36

    def GetProperty(self):
        return {"ZoomX": 1.25, "Opacity": 80, "Speed Change": 50, "Retime Process": "Optical Flow"}

    def GetMarkers(self):
        return {4: {"color": "Blue", "name": "Beat"}}

    def GetFlags(self):
        return ["Green"]

    def GetClipColor(self):
        return "Orange"

    def GetClipEnabled(self):
        return False

    def GetSelectedTakeIndex(self):
        return 1

    def GetTakesCount(self):
        return 1

    def GetTakeByIndex(self, index):
        assert index == 1
        return {"mediaPoolItem": _Media(), "startFrame": 12, "endFrame": 60}

    def GetLinkedItems(self):
        return []

    def GetMediaPoolItem(self):
        return _Media()

    def GetKeyframeCount(self, property_name):
        return 1 if property_name == "ZoomX" else 0

    def GetKeyframeAtIndex(self, property_name, index):
        assert property_name == "ZoomX" and index == 0
        return {"frame": 110, "interpolation": "bezier"}

    def GetPropertyAtKeyframeIndex(self, property_name, index):
        assert property_name == "ZoomX" and index == 0
        return 1.25

    def GetFusionCompCount(self):
        return 1

    def GetFusionCompByIndex(self, index):
        assert index == 1
        return _Comp()

    def GetNumNodes(self):
        return 1

    def GetNodeGraph(self):
        return self

    def GetNodeLabel(self, index):
        assert index == 1
        return "Primary"

    def GetNodeEnabled(self, index):
        assert index == 1
        return True

    def GetLUT(self, index):
        assert index == 1
        return "Film.cube"

    def GetToolsInNode(self, index):
        assert index == 1
        return ["Glow"]

    def GetVersionNameList(self, version_type):
        return ["Current"] if version_type == 0 else []

    def GetCurrentVersion(self):
        return {"versionName": "Current", "versionType": 0}

    def GetColorGroup(self):
        return _Group()


class _Timeline:
    def GetUniqueId(self):
        return "timeline-1"

    def GetName(self):
        return "Complex"

    def GetStartFrame(self):
        return 100

    def GetEndFrame(self):
        return 148

    def GetStartTimecode(self):
        return "01:00:00:00"

    def GetCurrentTimecode(self):
        return "01:00:00:12"

    def GetSetting(self):
        return {"timelineFrameRate": "24", "timelineResolutionWidth": "1920"}

    def GetMarkers(self):
        return {110: {"color": "Red", "name": "Review"}}

    def GetTrackCount(self, track_type):
        return 1 if track_type in {"video", "audio"} else 0

    def GetTrackName(self, track_type, index):
        return f"{track_type.title()} {index}"

    def GetIsTrackEnabled(self, _track_type, _index):
        return True

    def GetIsTrackLocked(self, _track_type, _index):
        return False

    def GetItemListInTrack(self, track_type, _index):
        return [_Item()] if track_type == "video" else []


class _Project:
    def GetUniqueId(self):
        return "project-1"

    def GetName(self):
        return "Inspection Project"


class _Conn:
    timeline = _Timeline()
    project = _Project()


def test_build_timeline_inspection_collects_rich_native_state_and_truthful_gaps(monkeypatch):
    cache_calls = {"audio": 0, "resolution": 0}
    monkeypatch.setattr(
        timeline_inspection_export.keyframe_db,
        "list_audio_volume_envelopes",
        lambda _conn, **_kwargs: cache_calls.__setitem__("audio", cache_calls["audio"] + 1) or {"envelopes": []},
    )
    monkeypatch.setattr(
        timeline_inspection_export.keyframe_db,
        "_timeline_resolution",
        lambda _conn: cache_calls.__setitem__("resolution", cache_calls["resolution"] + 1) or (1920, 1080),
    )
    monkeypatch.setattr(
        timeline_inspection_export.timeline_ops,
        "get_track_items",
        lambda _conn, track_type, _index, **_kwargs: ([{
            "timeline_item_unique_id": "item-1",
            "source_start_frame": 12,
            "source_end_frame_exclusive": 60,
            "source_frame_rate": "24",
            "retime_source": {"originFrame": 12, "availableRange": {"start": 0, "endExclusive": 240}},
            "retime_time_map_digest": "a" * 64,
        }] if track_type == "video" else []),
    )
    monkeypatch.setattr(
        timeline_inspection_export.timeline_ops,
        "_inspect_sdk_fairlight_state",
        lambda _conn: {
            "tracks": [{"track_index": 1, "level_db": {"status": "available", "value": -3.0}}],
            "buses": {"status": "unavailable", "reason": "readback_unavailable", "buses": []},
            "plan_readback": {"status": "available", "clips": []},
        },
    )
    monkeypatch.setattr(
        timeline_inspection_export.video_fade_readback,
        "list_video_fade_handles",
        lambda _conn: {"items": [{
            "itemId": "item-1",
            "status": "available",
            "fadeInFrames": 8,
            "fadeOutFrames": 12,
            "source": "Project.db fixture",
            "curveUnavailableReason": "fixture does not retain curve shape",
        }]},
    )
    monkeypatch.setattr(
        timeline_inspection_export.color_primary_readback,
        "list_color_primary_controls",
        lambda _conn: {"items": [{
            "itemId": "item-1",
            "status": "available",
            "hasGrade": True,
            "primaryControlsByNode": {"1": {"contrast": 1.1}},
            "valueDomain": "Project.db persisted Color parameter value",
        }]},
    )
    monkeypatch.setattr(
        timeline_inspection_export.color_resolvefx_readback,
        "list_color_resolvefx_state",
        lambda _conn: {
            "items": [{
                "itemId": "item-1",
                "status": "available",
                "effects": [{
                    "nodeStackLayerIndex": 1,
                    "nodeIndex": 1,
                    "effectId": "com.blackmagicdesign.resolvefx.glow",
                    "settings": [{"name": "blend", "status": "available", "type": "double", "value": 0.5}],
                    "unknownSettingCount": 0,
                }],
                "source": "exact persisted grade",
            }],
            "knownNodeStackLayers": [1],
            "unknownRemainder": [{
                "scope": "node_stack_layers_above_1",
                "status": "unavailable",
                "reason": "no_verified_project_db_layer_mapping",
            }],
            "identitySource": "exact native item identity",
            "route": "project_db_read_only",
        },
    )

    document = timeline_inspection_export.build_timeline_inspection(_Conn())

    assert document["schema"] == "cutagent.timeline-inspection/v1"
    assert document["purpose"] == "inspection_only"
    assert document["reconstructable"] is False
    assert document["snapshotConsistency"] == {
        "mode": "mixed_live_and_independently_sampled_persisted_state",
        "liveReadback": "DaVinci Resolve scripting and Fusion APIs at export time",
        "persistedReadback": "independent read-only Project.db transactions sampled at last saved or autosaved state",
        "persistedCrossReaderAtomicityVerified": False,
        "unsavedGuiEqualityVerified": False,
        "automaticSavePerformed": False,
    }
    item = document["tracks"][0]["items"][0]
    assert item["properties"]["ZoomX"] == 1.25
    assert item["enabled"] is False
    assert item["keyframes"]["ZoomX"] == [
        {"index": 0, "frame": 110, "value": 1.25, "interpolation": "bezier"}
    ]
    assert item["fusion"][0]["graph"] == {"nodes": []}
    assert item["color"]["nodes"][0]["effects"] == ["Glow"]
    assert item["color"]["versions"]["local"] == ["Current"]
    assert item["color"]["nodes"][0]["primaryControls"] == {"contrast": 1.1}
    assert item["color"]["resolveFx"]["effects"][0]["effectId"] == "com.blackmagicdesign.resolvefx.glow"
    assert item["takes"]["items"][0]["startFrame"] == 12
    assert item["retime"]["speedChange"] == 50
    assert item["retime"]["persistedTimeMapDigest"] == "a" * 64
    assert item["fades"]["video"]["fadeInFrames"] == 8
    assert item["source"]["authoritativeEndFrameExclusive"] == 60
    assert document["tracks"][0]["locked"] is False
    assert document["tracks"][1]["fairlight"]["track_index"] == 1
    gaps = {row["path"] for row in document["coverage"]["unreadableFields"]}
    assert "tracks.video[1].items[0].color.nodes[0].primaryControls" not in gaps
    assert "tracks.video[1].items[0].retime.curve" in gaps
    assert "tracks.video[1].locked" not in gaps
    assert "tracks.video[1].items[0].enabled" not in gaps
    assert "fairlight.automation" in gaps
    assert "fairlight.routing" in gaps
    assert "color.resolveFx.unknownRemainder[0].node_stack_layers_above_1" in gaps
    assert document["coverage"]["complete"] is False
    assert cache_calls == {"audio": 1, "resolution": 1}


def test_persisted_item_classification_uses_exact_reviewed_pretty_type():
    calls = []

    class _Persisted:
        def row(self, **kwargs):
            calls.append(kwargs)
            return {"PrettyType": "Fusion Title"}

    classification = timeline_inspection_export._persisted_item_classification(
        _Persisted(),
        track_type="video",
        track_index=2,
        identity="title-id",
        name="Text+",
        start=87684,
        duration=72,
    )

    assert classification == {
        "kind": "fusion_title",
        "prettyType": "Fusion Title",
        "source": "exact persisted item identity",
    }
    assert calls == [{
        "track_type": "video",
        "track_index": 2,
        "identity": "title-id",
        "name": "Text+",
        "start": 87684,
        "duration": 72,
    }]


def test_persisted_item_classification_does_not_infer_unreviewed_types():
    persisted = SimpleNamespace(row=lambda **_kwargs: {"PrettyType": "Compound Clip"})

    assert timeline_inspection_export._persisted_item_classification(
        persisted,
        track_type="video",
        track_index=1,
        identity="compound-id",
        name="Nested",
        start=100,
        duration=48,
    ) is None


def test_color_none_tool_result_is_readback_unavailable_not_unserializable():
    graph = SimpleNamespace(
        GetNumNodes=lambda: 1,
        GetToolsInNode=lambda _index: None,
        GetNodeLabel=lambda _index: "Primary",
        GetLUT=lambda _index: "",
    )
    item = SimpleNamespace(
        GetNodeGraph=lambda: graph,
        GetVersionNameList=lambda _kind: [],
        GetCurrentVersion=lambda: {},
        GetColorGroup=lambda: None,
    )
    collector = timeline_inspection_export._Collector()

    result = timeline_inspection_export._color(
        collector,
        item,
        "tracks.video[1].items[0]",
        {"status": "available", "primaryControlsByNode": {"1": {}}},
        None,
    )

    assert result["nodes"][0]["effects"] is None
    effect_gap = next(
        row for row in collector.unreadable
        if row["path"].endswith("color.nodes[0].effects")
    )
    assert effect_gap["reason"] == "readback_unavailable"


def test_persisted_audio_effects_preserves_unknown_payload_as_a_gap(monkeypatch):
    monkeypatch.setattr(
        timeline_inspection_export.audio_clip_effect_readback,
        "read_audio_clip_effects",
        lambda _cursor, **_kwargs: {
            "itemId": "audio-1",
            "clipFx": {
                "plugins": [{"pluginId": "bmd:Chorus:1", "name": "Chorus"}],
                "exactFixtureParameters": {},
                "unknownParameterRemainder": [{"pluginId": "bmd:Chorus:1", "names": ["BMDChorus::MIX"]}],
            },
            "archiveEq": None,
            "unknownEffectFilters": {"payloadSha256": "a" * 64, "payloadBytes": 10},
            "source": "exact persisted state",
        },
    )
    persisted = SimpleNamespace(connection=SimpleNamespace(cursor=lambda: object()))
    collector = timeline_inspection_export._Collector()

    result = timeline_inspection_export._persisted_audio_effects(
        collector, persisted, identity="audio-1", path="tracks.audio[1].items[0]",
    )

    assert result["clipFx"]["plugins"][0]["pluginId"] == "bmd:Chorus:1"
    reasons = {row["reason"] for row in collector.unreadable}
    assert reasons == {
        "parameter_values_not_strictly_decodable",
        "unrecognized_persisted_effect_filter_payload",
    }


def test_nested_structure_uses_exact_media_and_wrapper_ids_and_preserves_gaps(monkeypatch):
    calls = []
    monkeypatch.setattr(
        timeline_inspection_export.nested_media_db,
        "inspect_nested_media_graph",
        lambda project_db_path, **kwargs: calls.append((project_db_path, kwargs)) or {
            "status": "inspected",
            "media": {"media_id": "multicam-1", "kind": "multicam"},
            "tracks": [{"angle_index": 0, "items": []}],
            "nested_media": {
                "cycle": {"status": "unsupported", "reason": "nested_media_cycle"},
            },
            "unsupported": [
                {"path": "tracks[].items[].selector_blob", "reason": "selector_angle_semantics_not_decoded"},
            ],
        },
    )
    persisted = SimpleNamespace(project_db_path="/tmp/Project.db")
    collector = timeline_inspection_export._Collector()

    result = timeline_inspection_export._nested_structure(
        collector,
        persisted,
        domain="multicam",
        path="tracks.video[1].items[0]",
        media_id="multicam-1",
        wrapper_item_id="wrapper-1",
    )

    assert result["media"] == {"media_id": "multicam-1", "kind": "multicam"}
    assert calls == [("/tmp/Project.db", {
        "media_id": "multicam-1", "wrapper_item_id": "wrapper-1",
    })]
    assert collector.domain_counts["multicam"] == {"available": 1, "unavailable": 2}
    assert collector.unreadable == [{
        "domain": "multicam",
        "path": "tracks.video[1].items[0].multicam.angleStructure.unsupported[0].tracks[].items[].selector_blob",
        "reason": "selector_angle_semantics_not_decoded",
        "method": "strict persisted nested-media readback",
    }, {
        "domain": "multicam",
        "path": "tracks.video[1].items[0].multicam.angleStructure.nestedMedia[cycle]",
        "reason": "nested_media_cycle",
        "method": "strict persisted nested-media readback",
    }]


def test_write_timeline_inspection_is_atomic_private_and_requires_force(tmp_path, monkeypatch):
    monkeypatch.setattr(
        timeline_inspection_export,
        "build_timeline_inspection",
        lambda _conn: {"schema": timeline_inspection_export.SCHEMA, "coverage": {"complete": True, "unreadableFieldCount": 0, "domains": {"timeline": {"status": "available"}}}},
    )
    target = tmp_path / "inspection.json"

    receipt = timeline_inspection_export.write_timeline_inspection(object(), str(target))

    assert receipt["complete"] is True
    assert receipt["unreadable_field_count"] == 0
    assert json.loads(target.read_text())["schema"] == timeline_inspection_export.SCHEMA
    assert target.stat().st_mode & 0o077 == 0
    with pytest.raises(ValidationError, match="already exists"):
        timeline_inspection_export.write_timeline_inspection(object(), str(target))
    receipt = timeline_inspection_export.write_timeline_inspection(object(), str(target), force=True)
    assert receipt["byte_count"] == target.stat().st_size


def test_write_timeline_inspection_rejects_non_json_and_symlink(tmp_path, monkeypatch):
    monkeypatch.setattr(timeline_inspection_export, "build_timeline_inspection", lambda _conn: {})
    with pytest.raises(ValidationError, match="end in .json"):
        timeline_inspection_export.write_timeline_inspection(object(), str(tmp_path / "inspection.txt"))
    source = tmp_path / "source.json"
    source.write_text("{}")
    link = tmp_path / "inspection.json"
    link.symlink_to(source)
    with pytest.raises(ValidationError, match="symbolic link"):
        timeline_inspection_export.write_timeline_inspection(object(), str(link), force=True)


def test_db_fallbacks_bind_exact_item_identity_for_keyframes_and_retime(monkeypatch):
    calls = []

    class _Persisted:
        def row(self, **kwargs):
            calls.append(kwargs)
            return {"EffectFiltersBA": b"effects", "MediaTimemapBA": b"time-map"}

    class _Point:
        def to_dict(self, **kwargs):
            return {"frame": kwargs["item_start"] + 3, "value": 1.5}

    spec = SimpleNamespace(public_name="ZoomX")
    monkeypatch.setattr(timeline_inspection_export.keyframe_db, "_VIDEO_PROPERTY_SPECS", {"ZoomX": spec})
    monkeypatch.setattr(timeline_inspection_export.keyframe_db, "_decode_effect_filters", lambda _blob: (None, [object()]))
    monkeypatch.setattr(timeline_inspection_export.keyframe_db, "_row_keyframe_origin", lambda _row, _spec: 0)
    monkeypatch.setattr(timeline_inspection_export.keyframe_db, "_read_points_from_groups", lambda _groups, _spec, **_kwargs: [_Point()])
    monkeypatch.setattr(timeline_inspection_export.keyframe_db, "_timeline_resolution", lambda _conn: (1920, 1080))
    monkeypatch.setattr(
        timeline_inspection_export.clip_speed_db,
        "normalized_time_map_state",
        lambda _row, **_kwargs: {
            "native_record_origin_seconds": 0.5,
            "source_fps": 24.0,
        },
    )
    monkeypatch.setattr(
        timeline_inspection_export.retime_curve_readback,
        "curve_coordinates",
        lambda _state, **kwargs: {"points": [{"record": kwargs["record_start"], "source": kwargs["source_start"]}]},
    )
    collector = timeline_inspection_export._Collector()
    source = {"start": 100, "duration": 48}
    conn = SimpleNamespace(fps=24.0)

    keyframes = timeline_inspection_export._keyframes(
        collector, conn, _Persisted(), object(), "tracks.video[1].items[0]",
        track_type="video", item_name="Duplicate", identity="exact-item-id",
        track_index=1, authoritative_source=source, timeline_resolution=(1920, 1080),
    )
    curve = timeline_inspection_export._retime_curve(
        collector, conn, _Persisted(), "tracks.video[1].items[0]",
        track_type="video", track_index=1, item_name="Duplicate",
        identity="exact-item-id", authoritative_source=source,
    )

    assert keyframes == {"ZoomX": [{"frame": 103, "value": 1.5}]}
    assert curve == {"points": [{"record": 100, "source": 12.0}]}
    assert len(calls) == 2
    assert all(call["identity"] == "exact-item-id" for call in calls)
    assert all(call["track_index"] == 1 for call in calls)


def test_truncated_audio_envelope_cache_never_turns_an_omitted_item_into_empty_keyframes():
    collector = timeline_inspection_export._Collector()

    result = timeline_inspection_export._keyframes(
        collector,
        object(),
        None,
        object(),
        "tracks.audio[1].items[1]",
        track_type="audio",
        item_name="omitted.wav",
        identity="omitted-item",
        track_index=1,
        authoritative_source=None,
        audio_envelopes_by_id={"included-item": {"points": []}},
        audio_envelope_cache_complete=False,
    )

    assert result is None
    assert collector.unreadable[0]["reason"] == "native_and_db_readback_unavailable"


def test_collector_treats_none_as_unreadable_and_unprobed_as_not_applicable():
    collector = timeline_inspection_export._Collector()
    value = collector.call("timeline", "timeline.startFrame", SimpleNamespace(GetStartFrame=lambda: None), "GetStartFrame")

    report = collector.report()

    assert value is None
    assert report["complete"] is False
    assert report["domains"]["timeline"]["status"] == "unavailable"
    assert report["domains"]["fusion"]["status"] == "not_applicable"
    assert report["unreadableFields"] == [{
        "domain": "timeline",
        "method": "GetStartFrame",
        "path": "timeline.startFrame",
        "reason": "readback_unavailable",
    }]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_bounded_json_rejects_non_finite_numbers(value):
    with pytest.raises(ValueError, match="non-finite"):
        timeline_inspection_export._bounded_json({"value": value})


def test_bounded_json_accepts_realistic_nested_graphs_but_keeps_a_hard_depth_limit():
    value = "leaf"
    for _ in range(32):
        value = {"child": value}
    assert timeline_inspection_export._bounded_json(value) == value

    for _ in range(40):
        value = {"child": value}
    with pytest.raises(ValueError, match="maximum nesting depth"):
        timeline_inspection_export._bounded_json(value)


def test_persisted_reader_rejects_a_lookup_row_with_the_wrong_native_identity(monkeypatch):
    reader = timeline_inspection_export._PersistedItemReader(SimpleNamespace(timeline=_Timeline()))
    reader.connection = SimpleNamespace(cursor=lambda: object())
    monkeypatch.setattr(
        timeline_inspection_export.db_timeline_rows,
        "find_ti_item_row",
        lambda *_args, **_kwargs: {"Sm2TiItem_id": "wrong-item"},
    )

    with pytest.raises(LookupError, match="identity"):
        reader.row(
            track_type="video", track_index=1, identity="expected-item",
            name="Duplicate", start=100, duration=48,
        )


def test_21_1_inspection_uses_plural_properties_and_includes_native_fades(monkeypatch):
    monkeypatch.setattr(_Conn, "resolve", SimpleNamespace(GetVersion=lambda: [21, 1, 0]), raising=False)
    monkeypatch.setattr(_Item, "GetProperties", lambda self: {"AudioVolume": -6, "AudioPan": 25}, raising=False)
    monkeypatch.setattr(_Item, "GetFades", lambda self: {"FadeIn": 12.0, "FadeOut": 8.0}, raising=False)
    monkeypatch.setattr(_Item, "GetProperty", lambda self: pytest.fail("21.1 must use documented plural getter"))
    document = timeline_inspection_export._build_timeline_inspection(_Conn())
    # Native audio controls and faders must participate in exported snapshot state.
    encoded = json.dumps(document)
    assert '"AudioVolume": -6' in encoded
    assert '"AudioPan": 25' in encoded
    assert '"FadeIn": 12.0' in encoded
    assert '"FadeOut": 8.0' in encoded


def test_21_1_reads_native_retime_keys_and_does_not_require_db_fade_handles(monkeypatch):
    monkeypatch.setattr(_Conn, "resolve", SimpleNamespace(GetVersion=lambda: [21, 1, 0]), raising=False)
    monkeypatch.setattr(_Item, "GetProperties", lambda self: {"RetimeProcess": 2, "MotionEstimation": 3, "Scaling": 1}, raising=False)
    monkeypatch.setattr(_Item, "GetSpeed", lambda self: {"Percentage": 125.0, "PitchCorrection": True}, raising=False)
    monkeypatch.setattr(_Item, "GetFades", lambda self: {"FadeIn": 0, "FadeOut": 0}, raising=False)
    monkeypatch.setattr(_Item, "GetFlagList", lambda self: ["Blue"], raising=False)
    monkeypatch.setattr(timeline_inspection_export.video_fade_readback, "list_video_fade_handles", lambda *args: pytest.fail("native fades must not need DB"))
    document = timeline_inspection_export._build_timeline_inspection(_Conn())
    item = document["tracks"][0]["items"][0]
    assert item["retime"]["speedChange"] == 125.0
    assert item["retime"]["retimeProcess"] == 2
    assert item["retime"]["motionEstimation"] == 3
    assert item["retime"]["nativeSpeed"]["PitchCorrection"] is True
    assert item["flags"] == ["Blue"]
    assert item["fades"]["video"]["source"] == "TimelineItem.GetFades"
    assert not any(row["path"].endswith("fades.video.curve") for row in document["coverage"]["unreadableFields"])


def test_audio_native_fades_are_not_overwritten_by_saved_fairlight_snapshot():
    collector = timeline_inspection_export._Collector()
    item = {"identity": "audio-1", "fades": {"audio": {"fadeInFrames": 12, "fadeOutFrames": 18, "source": "TimelineItem.GetFades"}}}
    tracks = [{"type": "audio", "index": 1, "items": [item]}]
    state = {"tracks": [{"track_index": 1}], "plan_readback": {"clips": [{"item_id": "audio-1", "fade_in_frames": 0, "fade_out_frames": 0}]}}
    timeline_inspection_export._attach_fairlight(collector, tracks, state)
    assert item["fades"]["audio"]["fadeInFrames"] == 12
    assert item["fades"]["audio"]["fadeOutFrames"] == 18


@pytest.mark.parametrize("durations,expected_suffixes", [
    ((12, 18), {"in", "out"}),
    ((0, 0), set()),
    ((None, 0), {"fadeInFrames", "in"}),
    ((False, -1), {"fadeInFrames", "fadeOutFrames", "in", "out"}),
])
def test_audio_fade_coverage_preserves_unknown_durations_and_curves(durations, expected_suffixes):
    collector = timeline_inspection_export._Collector()
    fades = dict(zip(("fadeInFrames", "fadeOutFrames"), durations))
    tracks = [{"type": "audio", "index": 2, "items": [{"fades": {"audio": fades}}]}]
    timeline_inspection_export._audio_fade_coverage(collector, tracks)
    assert {row["path"].rsplit(".", 1)[-1] for row in collector.unreadable} == expected_suffixes
    assert fades["curve"] == {"in": None, "out": None}
    if durations == (None, 0):
        assert fades["fadeInFrames"] is None


def test_audio_fade_gaps_survive_failed_fairlight_readback():
    collector = timeline_inspection_export._Collector()
    tracks = [{"type": "audio", "index": 1, "items": [{"fades": {"audio": None}}]}]
    timeline_inspection_export._attach_fairlight(collector, tracks, None)
    timeline_inspection_export._audio_fade_coverage(collector, tracks)
    assert {row["path"] for row in collector.unreadable} == {
        "fairlight", "tracks.audio[1].items[0].fades.audio",
        "tracks.audio[1].fairlight", "tracks.audio[1].items[0].fairlight",
        "tracks.audio[1].items[0].fairlight.sourceChannelMapping",
    }


def test_fairlight_partial_controls_are_reported_without_inventing_defaults():
    collector = timeline_inspection_export._Collector()
    item = {"identity": "audio-1", "fades": {"audio": None}}
    tracks = [{"type": "audio", "index": 1, "items": [item]}]
    state = {
        "tracks": [{"track_index": 1, "level_db": {"status": "available", "value": 0},
                    "pan": {"status": "unavailable", "reason": "unsupported_pan_layout"}}],
        "plan_readback": {"clips": [{"item_id": "audio-1", "gain_db": None, "pan": 0,
                                      "effect_plugin_ids": [], "fade_in_frames": None, "fade_out_frames": 0}]},
    }
    timeline_inspection_export._attach_fairlight(collector, tracks, state)
    timeline_inspection_export._audio_fade_coverage(collector, tracks)
    gaps = {row["path"]: row["reason"] for row in collector.unreadable}
    assert gaps["tracks.audio[1].fairlight.pan"] == "unsupported_pan_layout"
    assert gaps["tracks.audio[1].items[0].fairlight.gain_db"] == "persisted_control_not_decoded"
    assert not any(path.endswith("effect_plugin_ids") or path.endswith("level_db") for path in gaps)
    assert item["fairlight"]["gain_db"] is None
    assert item["fairlight"]["pan"] == 0
    assert item["fairlight"]["effect_plugin_ids"] == []


def test_fusion_native_settings_include_all_tools_and_spline_handles():
    collector = timeline_inspection_export._Collector()
    class Comp(_Comp):
        def CopySettings(self, tools):
            assert tools == {}
            return {"Tools": {"SizeSpline": {"KeyFrames": {0: {1: 0.1, "RH": {1: 8, 2: 0.4}}, 24: {1: 0.8}}}}}
    item = SimpleNamespace(GetFusionCompCount=lambda: 1, GetFusionCompByIndex=lambda index: Comp())
    rows = timeline_inspection_export._fusion(collector, item, "item")
    assert rows[0]["nativeSettings"]["Tools"]["SizeSpline"]["KeyFrames"]["0"]["RH"]["2"] == 0.4
    assert not collector.unreadable


def test_full_fusion_settings_survive_compact_graph_read_failure(monkeypatch):
    collector = timeline_inspection_export._Collector()
    class Comp(_Comp):
        def CopySettings(self, tools):
            return {"Tools": {"CustomTool": {"Inputs": {"Value": 3}}}}
    monkeypatch.setattr(timeline_inspection_export.sdk_live_inspection, "_fusion_graph_evidence", lambda *args: (_ for _ in ()).throw(ValueError("unsupported compact input")))
    item = SimpleNamespace(GetFusionCompCount=lambda: 1, GetFusionCompByIndex=lambda index: Comp())
    rows = timeline_inspection_export._fusion(collector, item, "item")
    assert rows[0]["graph"] is None
    assert rows[0]["nativeSettings"]["Tools"]["CustomTool"]["Inputs"]["Value"] == 3
    assert collector.unreadable[0]["path"].endswith(".graph")


@pytest.mark.parametrize('persisted', [None, {'gain_db': -3, 'pan': 25}])
def test_live_audio_controls_override_saved_values_without_mutating_saved_state(persisted):
    collector = timeline_inspection_export._Collector()
    item = {'identity': 'a', 'properties': {'AudioVolume': -12.0, 'AudioPan': 0.0,
            'AudioVolumeEnabled': False, 'AudioPanEnabled': True}, 'fades': {'audio': {}}}
    tracks = [{'type': 'audio', 'index': 1, 'items': [item]}]
    saved = dict(persisted, item_id='a') if persisted else None
    state = {'tracks': [], 'plan_readback': {'clips': [saved] if saved else []}}
    timeline_inspection_export._attach_fairlight(collector, tracks, state)
    assert item['fairlight']['gain_db'] == -12
    assert item['fairlight']['pan'] == 0
    assert item['fairlight']['gain_db_enabled'] is False
    assert item['fairlight']['pan_enabled'] is True
    assert not any(r['path'].endswith(('.gain_db', '.pan')) for r in collector.unreadable if '.items[' in r['path'])
    if saved:
        assert saved['gain_db'] == -3
        assert saved['pan'] == 25
