"""Selected accepted eb54f8a45 regression and simulated fixtures; no native access."""
from __future__ import annotations
import sys,sqlite3,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'native'))
from cutagent_cli.core import edit_trim_db

class _Media:
    def __init__(self, uid: str, *, media_type: str = "Video + Audio", source_fps: float = 24.0) -> None:
        self.uid = uid
        self.media_type = media_type
        self.property_payload = {"Type": self.media_type, "FPS": str(source_fps)}

    def GetMediaId(self):
        return self.uid

    def GetClipProperty(self, key=None):
        if self.property_payload is not None:
            return self.property_payload
        return self.media_type if key == "Type" else {"Type": self.media_type}

class _Item:
    def __init__(self, uid: str, name: str, start: int, end: int, *, media_id: str, source_in: int = 0, right: int = 100, source_fps: float = 24.0, timeline_fps: float = 24.0, source_start: int | None = None, source_end: int | None = None) -> None:
        self.uid = uid
        self.name = name
        self.start = start
        self.end = end
        self.initial_start = start
        self.initial_end = end
        self.media = _Media(media_id, source_fps=source_fps)
        self.source_fps = source_fps
        self.timeline_fps = timeline_fps
        self.source_in = source_in
        self.right = right
        self.source_start = source_in if source_start is None else source_start
        self.source_end = self.source_start + round((end - start) * source_fps / timeline_fps) if source_end is None else source_end
        self.linked: list[_Item] = []

    def GetUniqueId(self): return self.uid
    def GetName(self): return self.name
    def GetStart(self, *_args): return self.start
    def GetEnd(self, *_args): return self.end
    def GetDuration(self): return self.end - self.start
    def GetMediaPoolItem(self): return self.media
    def GetLeftOffset(self): return self.source_in
    def GetRightOffset(self): return self.right
    def GetSourceStartFrame(self): return self.source_start + round((self.start - self.initial_start) * self.source_fps / self.timeline_fps)
    def GetSourceEndFrame(self): return self.source_end - 1 - round((self.initial_end - self.end) * self.source_fps / self.timeline_fps)
    def GetLinkedItems(self): return list(self.linked)

class _Timeline:
    def __init__(self, tracks, *, name="Trim QA", uid="timeline-1") -> None:
        self.tracks = tracks
        self.name = name
        self.uid = uid
        self.track_names = {
            (track_type, track_index): f"{track_type.title()} {track_index}"
            for track_type, track_index in tracks
        }
        self.track_enabled = {key: True for key in self.track_names}
        self.track_locked = {key: False for key in self.track_names}

    def GetName(self): return self.name
    def GetUniqueId(self): return self.uid
    def GetStartFrame(self): return 0
    def GetTrackCount(self, track_type):
        return max((index for kind, index in self.tracks if kind == track_type), default=0)
    def GetItemListInTrack(self, track_type, track_index):
        return list(self.tracks.get((track_type, track_index), []))
    def GetTrackName(self, track_type, track_index):
        return self.track_names.get((track_type, track_index), "")
    def GetIsTrackEnabled(self, track_type, track_index):
        return self.track_enabled.get((track_type, track_index))
    def GetIsTrackLocked(self, track_type, track_index):
        return self.track_locked.get((track_type, track_index))

class _Project:
    def __init__(self, name="Trim Project", uid="project-1") -> None:
        self.name = name
        self.uid = uid

    def GetName(self): return self.name
    def GetUniqueId(self): return self.uid

class _Conn:
    def __init__(self, tracks) -> None:
        self.timeline = _Timeline(tracks)
        self.project = _Project()
        self.fps = 24.0
        self.start_frame = 0
        self.refresh_callback = None

    def refresh(self):
        if self.refresh_callback is not None:
            self.refresh_callback(self)

def test_trim_verifier_accepts_one_source_frame_of_mixed_rate_end_quantization(tmp_path):
    baseline = _Item(
        "video", "shot.mov", 0, 148, media_id="media-1",
        source_fps=30000 / 1001, timeline_fps=50.0,
        source_start=30, source_end=119,
    )
    conn = _Conn({("video", 1): [baseline]})
    conn.fps = 50.0
    plan = edit_trim_db._preflight(
        conn, timeline_name=None, track_index=1, start_frame="0f",
        current_end_frame="148f", name="shot.mov", head_frames=0,
        tail_frames=1, linked_audio_mode="exclude",
    )
    changed = _Item(
        "video", "shot.mov", 0, 147, media_id="media-1",
        source_fps=30000 / 1001, timeline_fps=50.0,
        source_start=30, source_end=119, right=101,
    )
    changed_conn = _Conn({("video", 1): [changed]})
    changed_conn.fps = 50.0
    db_path = tmp_path / "Project.db"
    database = sqlite3.connect(db_path)
    database.execute('CREATE TABLE Sm2TiItem (Sm2TiItem_id TEXT PRIMARY KEY, Start TEXT, Duration TEXT, "In" TEXT)')
    database.execute("INSERT INTO Sm2TiItem VALUES (?, ?, ?, ?)", ("video", "0", "147", "0"))
    database.commit()
    database.close()
    # Use the production writer result, not a synthetic plan/result merge: the
    # native verifier must receive fps through the actual producer contract.
    db_helpers = edit_trim_db.timeline_item_duration_db
    with patch.object(db_helpers, "_fetch_db_row_for_live_target", return_value={}), \
         patch.object(db_helpers, "_transition_conflicts_for_item_range", return_value=[]), \
         patch.object(db_helpers, "_apply_duration_update", return_value={"item_id": "video", "name": "shot.mov"}):
        mutation = edit_trim_db._writer_for_plan(plan)(None, None, object())
    assert mutation["fps"] == 50.0

    result = edit_trim_db._verify_trim(
        changed_conn,
        mutation,
        type("Session", (), {"project_db_path": str(db_path)})(),
    )

    assert result["status"] == "verified"

class TrimQuantizationTests(unittest.TestCase):
    def test_mixed_rate_native_endpoint_quantization(self):
        with tempfile.TemporaryDirectory() as directory:
            test_trim_verifier_accepts_one_source_frame_of_mixed_rate_end_quantization(Path(directory))
