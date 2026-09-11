"""Exact native target and public state projection for output blanking."""
from .timeline_read_prepared_action import _digest
from ..core import output_blanking


def target(conn, value):
    requested = value.get('timelineItemId')
    if requested is None:
        return None
    matches = [item for index in range(1, conn.timeline.GetTrackCount('video') + 1)
               for item in conn.timeline.GetItemListInTrack('video', index) or []
               if item.GetType() == 'video' and _digest('timeline_item_', {'timelineId': value['timelineId'], 'nativeId': str(item.GetUniqueId())}) == requested]
    if len(matches) != 1:
        raise ValueError('Output blanking requires one exact video timeline item.')
    return matches[0]


def read(conn, value):
    raw = output_blanking.read(conn, target(conn, value))
    return {'blanking': raw['blanking'], 'useTimeline': raw.get('use_timeline'),
            'effectiveBlanking': raw.get('effective_blanking', raw['blanking'])}


def write(conn, value):
    return output_blanking.write(conn, value['operation'].get('blanking'), item=target(conn, value), use_timeline=value['operation'].get('useTimeline'))
