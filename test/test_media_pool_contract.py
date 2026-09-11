# Contract fixtures reconciled from canonical CutAgent commit 2703be002.
from __future__ import annotations

import json
import os
import time

import pytest

from cutagent_cli.commands.media import _require_sdk_exact_import_file
from cutagent_cli.core.sdk_live_inspection import (
    inspect_live_state,
    require_media_pool_mutation_guard,
    require_project_mutation_guard,
)
from cutagent_cli.core.media_pool import get_transcription, normalize_transcription
from cutagent_cli.errors import APICallFailed, CapabilityNegotiationFailed, SdkMutationStaleRevision


def test_sdk_exact_import_file_rejects_directories_and_symlinks(tmp_path):
    media_file = tmp_path / "A.mov"
    media_file.write_bytes(b"fixture")
    assert _require_sdk_exact_import_file(str(media_file)) == os.path.realpath(media_file)

    with pytest.raises(CapabilityNegotiationFailed) as directory_error:
        _require_sdk_exact_import_file(str(tmp_path))
    assert getattr(directory_error.value, "code", None) == "CAPABILITY_NEGOTIATION_FAILED"

    media_link = tmp_path / "linked.mov"
    media_link.symlink_to(media_file)
    with pytest.raises(CapabilityNegotiationFailed) as symlink_error:
        _require_sdk_exact_import_file(str(media_link))
    assert getattr(symlink_error.value, "code", None) == "CAPABILITY_NEGOTIATION_FAILED"


def test_sdk_exact_import_file_requires_the_inspected_file_identity(tmp_path):
    media_file = tmp_path / "A.mov"
    media_file.write_bytes(b"fixture")
    file_info = os.lstat(media_file)
    identity = json.dumps({
        "device": str(file_info.st_dev),
        "inode": str(file_info.st_ino),
        "size": str(file_info.st_size),
        "modifiedNanoseconds": str(file_info.st_mtime_ns),
    })
    assert _require_sdk_exact_import_file(str(media_file), identity) == os.path.realpath(media_file)

    media_file.write_bytes(b"replacement")
    with pytest.raises(CapabilityNegotiationFailed) as changed_error:
        _require_sdk_exact_import_file(str(media_file), identity)
    assert getattr(changed_error.value, "code", None) == "CAPABILITY_NEGOTIATION_FAILED"


class Asset:
    def __init__(self, name: str, native_id: str | None, *, unique_id=None, metadata=None, selected=False, media_type="Video", source_path=None):
        self.name = name
        self.native_id = native_id
        self.unique_id = unique_id
        self.metadata = metadata or {}
        self.selected = selected
        self.media_type = media_type
        self.source_path = source_path
        self.transcription = None
        self.transcription_calls = []

    def GetName(self):
        return self.name

    def GetMediaId(self):
        return self.native_id

    def GetUniqueId(self):
        return self.unique_id

    def GetClipProperty(self):
        return {
            "Type": self.media_type,
            "File Path": self.source_path or f"/private/camera/{self.name}",
            "Duration": "120",
            "Resolution": "3840x2160",
            "FPS": "23.976",
            "Start TC": "01:00:00:00",
        }

    def GetMetadata(self):
        return self.metadata

    def GetTranscription(self, use_nested_clip_transcription=False):
        self.transcription_calls.append(use_nested_clip_transcription)
        return self.transcription() if callable(self.transcription) else self.transcription


class Folder:
    def __init__(self, name: str, native_id: str | None = None, *, clips=None, children=None):
        self.name = name
        self.native_id = native_id
        self.clips = clips or []
        self.children = children or []

    def GetName(self):
        return self.name

    def GetUniqueId(self):
        return self.native_id

    def GetClipList(self):
        return self.clips

    def GetSubFolderList(self):
        return self.children


class MediaPool:
    def __init__(self, root: Folder, selected=None):
        self.root = root
        self.selected = selected or []

    def GetRootFolder(self):
        return self.root

    def GetSelectedClips(self):
        return self.selected


class Project:
    def GetName(self):
        return "Editorial"

    def GetUniqueId(self):
        return "native-project"

    def GetTimelineCount(self):
        return 0


class Connection:
    def __init__(self, root: Folder, selected=None):
        self.project = Project()
        self.timeline = None
        self.media_pool = MediaPool(root, selected)
        self.refresh_count = 0

    def refresh(self):
        self.refresh_count += 1


def test_timeline_list_live_inspection_brackets_complete_authoritative_inventory():
    conn = Connection(Folder("Master"))
    rows = [
        {"index": 1, "name": "Main", "timeline_id": "timeline-native-1", "is_current": False},
        {"index": 2, "name": "Alt", "timeline_id": "timeline-native-2", "is_current": False},
    ]
    inspected = inspect_live_state(
        conn,
        "timeline.list",
        deadline_at_ms=int(time.time() * 1000) + 10_000,
        list_timelines=lambda *_args, **kwargs: rows if kwargs.get("authoritative_ids") is True else [],
        summarize_timeline=lambda *_args, **_kwargs: {},
    )
    assert inspected["before"]["timelines"] == rows
    assert inspected["after"]["timelines"] == rows
    assert inspected["summary"] is None
    assert conn.refresh_count == 1


def test_project_and_media_pool_guards_reject_state_drift_before_sdk_mutation(monkeypatch):
    conn = Connection(Folder("Master", clips=[Asset("A.mov", "asset-a")]))
    conn.project_manager = type("ProjectManager", (), {
        "GetCurrentDatabase": lambda _self: {"DbName": "Local", "DbType": "Disk"},
    })()
    deadline = int(time.time() * 1000) + 10_000
    project_inspection = inspect_live_state(
        conn,
        "project.context",
        deadline_at_ms=deadline,
        list_timelines=lambda *_args, **_kwargs: [],
        summarize_timeline=lambda *_args, **_kwargs: {},
    )
    media_inspection = inspect(conn)
    monkeypatch.setenv("CUTAGENT_SDK_PROJECT_GUARD", project_inspection["mutation_guard"])
    monkeypatch.setenv("CUTAGENT_SDK_MEDIA_POOL_GUARD", media_inspection["mutation_guard"])
    require_project_mutation_guard(conn, list_timelines=lambda *_args, **_kwargs: [])
    require_media_pool_mutation_guard(conn)

    conn.project.GetName = lambda: "Another project"
    conn.media_pool.root.clips.append(Asset("B.mov", "asset-b"))
    with pytest.raises(SdkMutationStaleRevision):
        require_project_mutation_guard(conn, list_timelines=lambda *_args, **_kwargs: [])
    with pytest.raises(SdkMutationStaleRevision):
        require_media_pool_mutation_guard(conn)


def test_project_context_preserves_private_postgresql_library_address():
    conn = Connection(Folder("Master"))
    conn.project_manager = type("ProjectManager", (), {
        "GetCurrentDatabase": lambda _self: {
            "DbName": "Shared", "DbType": "PostgreSQL", "IpAddress": "10.0.0.7",
        },
    })()
    inspected = inspect_live_state(
        conn,
        "project.context",
        deadline_at_ms=int(time.time() * 1000) + 10_000,
        list_timelines=lambda *_args, **_kwargs: [],
        summarize_timeline=lambda *_args, **_kwargs: {},
    )
    assert inspected["after"]["library"] == {
        "name": "Shared", "kind": "postgresql", "address": "10.0.0.7",
    }


def inspect(conn, *, offset=0, page_size=32, search=None):
    return inspect_live_state(
        conn,
        "mediaPool.page",
        deadline_at_ms=int(time.time() * 1000) + 10_000,
        list_timelines=lambda *_args, **_kwargs: [],
        summarize_timeline=lambda *_args, **_kwargs: {},
        offset=offset,
        page_size=page_size,
        search=search,
    )


def test_media_pool_transcription_normalizes_documented_21_1_shape_and_empty_state():
    assert normalize_transcription({}) == {"available": False, "language": None, "segments": []}
    clip = Asset("Interview.wav", "asset-a")
    clip.transcription = {
        "language": "en-US",
        "segments": [{
            "start": "01:00:00:00",
            "end": "01:00:01:00",
            "text": "Hello world",
            "speaker": "Speaker 1",
            "words": [
                {"start": "01:00:00:00", "end": "01:00:00:12", "text": "Hello"},
                {"start": "01:00:00:13", "end": "01:00:01:00", "text": "world"},
            ],
        }],
    }
    conn = Connection(Folder("Master", clips=[clip]))
    conn.media_pool.GetCurrentFolder = lambda: conn.media_pool.root

    result = get_transcription(conn, clip_name="Interview.wav", use_nested_clip_transcription=True)

    assert result == {
        "clip": "Interview.wav",
        "folder": "Master",
        "use_nested_clip_transcription": True,
        "available": True,
        "language": "en-US",
        "segments": clip.transcription["segments"],
    }
    assert clip.transcription_calls == [True]


def test_media_pool_transcription_rejects_malformed_and_unbounded_native_shapes():
    with pytest.raises(APICallFailed, match="malformed transcription segment"):
        normalize_transcription({"segments": ["not-a-segment"]})
    with pytest.raises(APICallFailed, match="bounded contract"):
        normalize_transcription({"segments": [{"words": [{}] * 100_001}]})


def test_sdk_media_pool_transcription_targets_native_identity_and_brackets_readback():
    target = Asset("Interview.wav", "asset-target")
    target.transcription = {"language": "en-US", "segments": []}
    other = Asset("Interview.wav", "asset-other")
    other.transcription = {"language": "fr-FR", "segments": []}
    conn = Connection(Folder("Master", clips=[other, target]))

    inspected = inspect_live_state(
        conn,
        "mediaPool.transcription",
        deadline_at_ms=int(time.time() * 1000) + 10_000,
        list_timelines=lambda *_args, **_kwargs: [],
        summarize_timeline=lambda *_args, **_kwargs: {},
        media_pool_native_id="asset-target",
        use_nested_clip_transcription=True,
    )

    assert inspected["summary"] == {"available": True, "language": "en-US", "segments": []}
    assert target.transcription_calls == [True, True]
    assert other.transcription_calls == []

    calls = 0
    def drifting_transcription():
        nonlocal calls
        calls += 1
        return {"language": "en-US", "segments": [] if calls == 1 else [{"text": "changed"}]}
    target.transcription = drifting_transcription
    with pytest.raises(SdkMutationStaleRevision):
        inspect_live_state(
            conn,
            "mediaPool.transcription",
            deadline_at_ms=int(time.time() * 1000) + 10_000,
            list_timelines=lambda *_args, **_kwargs: [],
            summarize_timeline=lambda *_args, **_kwargs: {},
            media_pool_native_id="asset-target",
        )


def test_multicam_inspection_is_bracketed_and_rejects_state_drift():
    conn = Connection(Folder("Master"))
    stable = {
        "name": "Interview Multicam",
        "native_id": "native-multicam",
        "angles": [
            {"angle_index": 0, "label": "Angle 1", "sources": [{"name": "A.mov", "native_id": "native-a"}]},
            {"angle_index": 1, "label": "Angle 2", "sources": [{"name": "B.mov", "native_id": "native-b"}]},
        ],
    }
    result = inspect_live_state(
        conn,
        "multicam.inspect",
        deadline_at_ms=int(time.time() * 1000) + 10_000,
        list_timelines=lambda *_args, **_kwargs: [],
        summarize_timeline=lambda *_args, **_kwargs: {},
        multicam_name="Interview Multicam",
        inspect_multicam=lambda *_args: stable,
    )
    assert result["summary"] == stable
    assert conn.refresh_count == 1

    calls = 0

    def drifting(*_args):
        nonlocal calls
        calls += 1
        return {**stable, "name": "Interview Multicam" if calls == 1 else "Retargeted Multicam"}

    with pytest.raises(SdkMutationStaleRevision):
        inspect_live_state(
            conn,
            "multicam.inspect",
            deadline_at_ms=int(time.time() * 1000) + 10_000,
            list_timelines=lambda *_args, **_kwargs: [],
            summarize_timeline=lambda *_args, **_kwargs: {},
            multicam_name="Interview Multicam",
            inspect_multicam=drifting,
        )


def test_media_pool_page_is_bounded_sorted_and_carries_curated_metadata():
    selected = Asset(
        "A.mov",
        "asset-a",
        metadata={"Scene": "12", "Camera #": "A", "Camera": "duplicate", "Private Key": "secret"},
    )
    root = Folder(
        "Master",
        clips=[Asset("Z.mov", None), selected],
        children=[Folder("B roll", clips=[Asset("B.mov", "asset-b")])],
    )
    conn = Connection(root, [selected])

    first = inspect(conn, page_size=3)["summary"]
    second = inspect(conn, offset=3, page_size=3)["summary"]

    assert first["total"] == 5
    assert first["next_offset"] == 3
    assert len(first["entries"]) == 3
    assert [entry["name"] for entry in first["entries"]] == ["Master", "A.mov", "Z.mov"]
    assert first["entries"][1]["selected"] is True
    assert first["entries"][1]["kind"] == "video"
    assert first["entries"][1]["metadata_available"] is True
    assert first["entries"][1]["metadata"] == [
        {"key": "scene", "value": "12"},
        {"key": "camera", "value": "A"},
    ]
    assert first["entries"][1]["source_file_name"] == "A.mov"
    assert "source_path" not in first["entries"][1]
    assert second["entries"][0]["name"] == "B roll"
    assert second["next_offset"] is None
    assert first["pool_digest"] == second["pool_digest"]
    assert conn.refresh_count == 2


@pytest.mark.parametrize("media_type", ["Fusion Title", "Fusion Composition"])
def test_media_pool_generated_fusion_assets_report_metadata_unavailable(media_type):
    asset = Asset("Generated", "generated-id", media_type=media_type)
    asset.GetClipProperty = lambda: {"Type": media_type, "File Path": ""}
    asset.GetMetadata = lambda: None

    page = inspect(Connection(Folder("Master", clips=[asset])))["summary"]

    assert page["entries"][1]["metadata_available"] is False
    assert page["entries"][1]["metadata"] == []


@pytest.mark.parametrize(
    ("media_type", "source_path"),
    [("Video", ""), ("Fusion Title", "/media/generated.setting"), ("Generator", ""),
     ("Fusion Title", 0), ("Fusion Title", False), ("Fusion Title", []), ({}, "")],
)
def test_media_pool_unqualified_null_metadata_stays_fail_closed(media_type, source_path):
    asset = Asset("Asset", "asset-id", media_type=media_type)
    asset.GetClipProperty = lambda: {"Type": media_type, "File Path": source_path}
    asset.GetMetadata = lambda: None

    with pytest.raises(APICallFailed, match="GetMetadata returned an invalid"):
        inspect(Connection(Folder("Master", clips=[asset])))


def test_media_pool_metadata_search_rejects_unavailable_generated_metadata():
    asset = Asset("Generated", "generated-id", media_type="Fusion Title")
    asset.GetClipProperty = lambda: {"Type": "Fusion Title", "File Path": ""}
    asset.GetMetadata = lambda: None

    with pytest.raises(APICallFailed, match="did not expose metadata for every asset"):
        inspect(Connection(Folder("Master", clips=[asset])), search={
            "query": "scene",
            "match": "contains",
            "fields": ["metadata"],
        })

    by_name = inspect(Connection(Folder("Master", clips=[asset])), search={
        "query": "Generated",
        "match": "exact",
        "fields": ["name"],
    })["summary"]
    assert by_name["total"] == 1
    assert by_name["entries"][0]["name"] == "Generated"
    assert by_name["entries"][0]["metadata_available"] is False


def test_media_pool_page_carries_distinct_private_media_and_unique_identities():
    timeline = Asset(
        "Main",
        "timeline-media-id",
        unique_id="timeline-unique-id",
        media_type="Timeline",
    )
    conn = Connection(Folder("Master", clips=[timeline]))

    page = inspect(conn)["summary"]

    assert page["entries"][1]["native_id"] == "timeline-media-id"
    assert page["entries"][1]["unique_id"] == "timeline-unique-id"


def test_media_pool_page_treats_resolve_none_selection_as_authoritative_empty():
    conn = Connection(Folder("Master", clips=[Asset("A.mov", "asset-a")]))
    conn.media_pool.selected = None

    page = inspect(conn)["summary"]

    assert page["total"] == 2
    assert page["entries"][1]["name"] == "A.mov"
    assert page["entries"][1]["selected"] is False


def test_media_pool_revision_excludes_transient_selection_but_returns_fresh_selection():
    first = Asset("A.mov", "asset-a")
    second = Asset("B.mov", "asset-b")
    conn = Connection(Folder("Master", clips=[first, second]), [first])

    def refresh():
        conn.refresh_count += 1
        conn.media_pool.selected = [second]

    conn.refresh = refresh
    page = inspect(conn)["summary"]

    assert page["ambiguous_native_ids"] is False
    assert page["total"] == 3
    assert [entry["name"] for entry in page["entries"]] == ["Master", "A.mov", "B.mov"]
    assert [entry["selected"] for entry in page["entries"][1:]] == [False, True]


def test_media_pool_refresh_returns_current_metadata_without_duplicate_scan():
    asset = Asset("A.mov", "asset-a", metadata={"Scene": "12"})
    conn = Connection(Folder("Master", clips=[asset]))

    def refresh():
        conn.refresh_count += 1
        asset.metadata = {"Scene": "13"}

    conn.refresh = refresh
    page = inspect(conn)["summary"]
    assert page["entries"][1]["metadata"] == [{"key": "scene", "value": "13"}]
    assert conn.refresh_count == 1


def test_media_pool_combined_video_audio_type_is_normalized_as_video():
    conn = Connection(Folder("Master", clips=[Asset(
        "A.mov",
        "asset-a",
        media_type="Video + Audio",
        source_path=r"C:\Users\Alice\private\A.mov",
    )]))

    page = inspect(conn)["summary"]

    assert page["entries"][1]["kind"] == "video"
    assert page["entries"][1]["source_file_name"] == "A.mov"
    assert "source_path" not in page["entries"][1]


def test_media_pool_search_is_deterministic_and_large_pool_output_stays_bounded():
    assets = [Asset(f"Camera-{index:04d}.mov", f"asset-{index}", metadata={"Scene": str(index % 10)}) for index in range(501)]
    conn = Connection(Folder("Master", clips=list(reversed(assets))))

    page = inspect(conn, page_size=17, search={
        "query": "Camera-",
        "match": "contains",
        "fields": ["name"],
    })["summary"]

    assert page["total"] == 501
    assert len(page["entries"]) == 17
    assert page["next_offset"] == 17
    assert page["search"] == {
        "query": "Camera-",
        "match": "contains",
        "fields": ["name"],
    }
    assert [row["name"] for row in page["entries"][:3]] == [
        "Camera-0000.mov",
        "Camera-0001.mov",
        "Camera-0002.mov",
    ]


def test_media_pool_identity_ambiguity_and_invalid_page_bounds_are_explicit():
    conn = Connection(Folder("Master", clips=[Asset("A.mov", "duplicate"), Asset("B.mov", "duplicate")]))
    assert inspect(conn)["summary"]["ambiguous_native_ids"] is True

    with pytest.raises(Exception, match="beyond the current bounded result set"):
        inspect(conn, offset=99)

    with pytest.raises(Exception, match="from 1 through 32"):
        inspect(conn, page_size=33)


# Transient selection fallback is covered by test_native_inspection.py.
@pytest.mark.parametrize("failing_method", ["GetClipList", "GetSubFolderList"])
def test_media_pool_required_hierarchy_reads_fail_closed(failing_method):
    conn = Connection(Folder("Master", clips=[Asset("A.mov", "asset-a")]))
    target = conn.media_pool if failing_method == "GetSelectedClips" else conn.media_pool.root

    def fail():
        raise RuntimeError("native read failed")

    setattr(target, failing_method, fail)

    with pytest.raises(APICallFailed, match=failing_method):
        inspect(conn)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", "x" * 4097, "oversized Media Pool asset name"),
        ("source_path", "/private/" + "x" * 32_769, "oversized Media Pool source path"),
        ("metadata", {"Description": "x" * 65_537}, "oversized Media Pool metadata value"),
    ],
)
def test_media_pool_native_text_is_bounded_before_page_serialization(field, value, message):
    asset = Asset("A.mov", "asset-a")
    if field == "name":
        asset.name = value
    elif field == "source_path":
        asset.source_path = value
    else:
        asset.metadata = value
    conn = Connection(Folder("Master", clips=[asset]))

    with pytest.raises(APICallFailed, match=message):
        inspect(conn)


def test_timeline_facade_transcription_preserves_native_target_and_nested_flag(monkeypatch):
    from cutagent_cli.core import timeline_ops

    target = Asset("Interview.wav", "asset-target")
    target.transcription = {"language": "en-US", "segments": []}
    other = Asset("Interview.wav", "asset-other")
    conn = Connection(Folder("Master", clips=[other, target]))
    monkeypatch.setattr(timeline_ops, "list_timelines", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(timeline_ops, "summarize_timeline", lambda *_args, **_kwargs: {})
    result = timeline_ops.inspect_sdk_live_state(
        conn, "mediaPool.transcription", media_pool_native_id="asset-target",
        use_nested_clip_transcription=True,
    )
    assert result["summary"] == {"available": True, "language": "en-US", "segments": []}
    assert target.transcription_calls == [True, True]
    assert other.transcription_calls == []
