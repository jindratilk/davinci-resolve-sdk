"""Ownership and cleanup of temporary native retime reference resources."""

from __future__ import annotations

from typing import Any
import uuid

from ..errors import APICallFailed
from . import timeline_duplicate as duplicate


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise APICallFailed(message, recoverability="manual")


class ReferenceWorkspace:
    """Track native-returned identities; never infer ownership from a name."""

    def __init__(self, conn: Any):
        self.conn = conn
        self.name = f"CutAgent reference {uuid.uuid4().hex}"
        self.project_name = str(conn.project.GetName())
        self.project_id = conn.project.GetUniqueId()
        self.original = conn.project.GetCurrentTimeline()
        self.original_id = duplicate._timeline_identity(self.original)
        self.original_playhead = duplicate._playhead(self.original)
        self.original_folder_id = duplicate._folder_identity(conn.media_pool.GetCurrentFolder())
        self.before_timelines = duplicate._timeline_inventory(conn)
        self.before_ids = {row["identity"] for row in self.before_timelines}
        self.before_pool = duplicate._media_pool_snapshot(conn)
        _require(bool(self.project_id and self.original_id and self.original_folder_id) and None not in self.before_ids,
                 "Reference preparation requires exact original timeline and folder identities.")
        _require(not self.before_pool["unkeyed"] and not self.before_pool["unkeyed_folders"],
                 "Reference preparation requires an identifiable Media Pool inventory.")
        self.timeline_ids: set[str] = set()
        self.clip_ids: set[str] = set()
        self.folder_id: str | None = None

    def open(self) -> None:
        folder = self.conn.media_pool.AddSubFolder(self.conn.media_pool.GetRootFolder(), self.name)
        folder_id = duplicate._folder_identity(folder)
        _require(bool(folder_id) and folder_id not in self.before_pool["folders"],
                 "Native reference folder creation did not return a new folder identity.")
        self.folder_id = folder_id
        _require(self.conn.media_pool.SetCurrentFolder(folder) is True,
                 "Native reference preparation could not select its temporary folder.")

    def register_timeline(self, timeline: Any) -> str:
        identity = duplicate._timeline_identity(timeline)
        _require(bool(identity) and identity not in self.before_ids and identity not in self.timeline_ids,
                 "Native reference creation did not return a distinct temporary timeline.")
        self.timeline_ids.add(identity)
        # Returned timeline items establish ownership of imported compound
        # media. Pre-existing media are always excluded from deletion.
        objects = []
        getter = getattr(timeline, "GetMediaPoolItem", None)
        if callable(getter):
            objects.append(getter())
        for kind in ("video", "audio"):
            for track in range(1, int(timeline.GetTrackCount(kind) or 0) + 1):
                for item in timeline.GetItemListInTrack(kind, track) or []:
                    objects.append(item.GetMediaPoolItem())
        for media in objects:
            media_id = duplicate._clip_identity(media) if media is not None else None
            if media_id and media_id not in self.before_pool["clips"]:
                self.clip_ids.add(media_id)
        return identity

    def timeline(self, identity: str) -> Any:
        matches = [row for row in duplicate._timeline_inventory(self.conn) if row["identity"] == identity]
        _require(len(matches) == 1, "Native reference timeline identity could not be read back exactly.")
        return matches[0]["timeline"]

    def activate(self, identity: str) -> Any:
        timeline = self.timeline(identity)
        duplicate._switch_exact(self.conn, timeline, expected_name=str(timeline.GetName()))
        _require(duplicate._timeline_identity(self.conn.project.GetCurrentTimeline()) == identity,
                 "Native reference activation did not preserve the selected timeline identity.")
        return timeline

    def cleanup(self, conn: Any | None = None) -> None:
        """Delete only registered resources, restore selection, prove no leftovers."""
        if conn is not None:
            self.conn = conn
        _require(str(self.conn.project.GetName()) == self.project_name and self.conn.project.GetUniqueId() == self.project_id,
                 "Reference cleanup cannot operate after the active project changed.")
        original = self.activate(self.original_id)
        restoration = duplicate._restore_original(
            self.conn, original, name=str(original.GetName()), playhead=self.original_playhead,
        )
        _require(restoration.get("ok") is True,
                 "Reference cleanup could not restore the original timeline and playhead.")
        current_ids = {row["identity"] for row in duplicate._timeline_inventory(self.conn)}
        _require(self.before_ids.issubset(current_ids),
                 "Reference cleanup found a missing pre-existing timeline.")
        # Before deleting imported media, exclude any use by a surviving
        # timeline. This also protects user edits made while a reference ran.
        for row in duplicate._timeline_inventory(self.conn):
            if row["identity"] in self.timeline_ids:
                continue
            timeline = row["timeline"]
            for kind in ("video", "audio"):
                for track in range(1, int(timeline.GetTrackCount(kind) or 0) + 1):
                    for item in timeline.GetItemListInTrack(kind, track) or []:
                        media = item.GetMediaPoolItem()
                        media_id = duplicate._clip_identity(media) if media is not None else None
                        _require(media_id not in self.clip_ids,
                                 "Reference cleanup found temporary media used by a surviving timeline.")
        owned = [self.timeline(identity) for identity in self.timeline_ids if identity in current_ids]
        if owned:
            _require(self.conn.media_pool.DeleteTimelines(owned) is True,
                     "Native reference timelines could not be removed.")
        pool = duplicate._media_pool_snapshot(self.conn)
        leftover_media = [pool["clips"][identity]["object"] for identity in self.clip_ids if identity in pool["clips"]]
        if leftover_media:
            _require(self.conn.media_pool.DeleteClips(leftover_media) is True,
                     "Native reference media could not be removed.")
        pool = duplicate._media_pool_snapshot(self.conn)
        original_folder = pool["folders"].get(self.original_folder_id)
        _require(original_folder is not None and self.conn.media_pool.SetCurrentFolder(original_folder["object"]) is True,
                 "Reference cleanup could not restore the original Media Pool folder.")
        _require(duplicate._folder_identity(self.conn.media_pool.GetCurrentFolder()) == self.original_folder_id,
                 "Reference cleanup could not verify the restored Media Pool folder.")
        folder = pool["folders"].get(self.folder_id)
        if folder:
            # Unknown contents are not ours to delete recursively.
            _require(not folder["object"].GetClipList() and not folder["object"].GetSubFolderList(),
                     "Reference folder contains resources whose ownership is unproven.")
            _require(self.conn.media_pool.DeleteFolders([folder["object"]]) is True,
                     "Native reference folder could not be removed.")
        after = duplicate._media_pool_snapshot(self.conn)
        _require(set(after["clips"]) == set(self.before_pool["clips"])
                 and set(after["folders"]) == set(self.before_pool["folders"])
                 and not after["unkeyed"] and not after["unkeyed_folders"],
                 "Reference cleanup did not restore the original Media Pool inventory.")
        _require(all(after["clips"][identity]["description"] == row["description"]
                     for identity, row in self.before_pool["clips"].items()),
                 "Reference cleanup found changed pre-existing media metadata.")
        _require({row["identity"] for row in duplicate._timeline_inventory(self.conn)} == self.before_ids,
                 "Reference cleanup did not restore the original timeline inventory.")
