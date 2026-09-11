"""Documented DaVinci Resolve 21.1 output blanking in integer pixels."""
from __future__ import annotations

from contextlib import contextmanager
import math

from ..errors import APICallFailed, ValidationError
from . import resolve_api_version, timeline_ops

_EDGES = ('top', 'bottom', 'left', 'right')


@contextmanager
def _preserve_render_context(conn):
    """Keep documented blanking getters from changing Deliver settings."""
    from . import render_engine

    snapshot = render_engine._snapshot_render_context_with_preset(conn)
    try:
        yield
    finally:
        render_engine._restore_render_context(
            conn, snapshot, require_deliver_page=False
        )


def _require_api(conn):
    if not resolve_api_version.at_least(conn, 21, 1):
        raise ValidationError('Output blanking requires DaVinci Resolve 21.1 or later.')


def edges(value):
    """Normalize integral native floats without accepting fractional/negative pixels."""
    if not isinstance(value, dict) or set(value) != set(_EDGES):
        raise ValidationError('Output blanking requires top, bottom, left and right pixel values.')
    result = {}
    for key, number in value.items():
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number < 0 or number != int(number):
            raise ValidationError('Output blanking values must be nonnegative integer pixels.')
        result[key] = int(number)
    return result


def _native_edges(target):
    raw = target.GetOutputBlanking()
    if not isinstance(raw, dict):
        raise APICallFailed('DaVinci Resolve returned invalid output blanking.')
    try:
        return edges({str(key).lower(): value for key, value in raw.items()})
    except ValidationError as exc:
        raise APICallFailed('DaVinci Resolve returned incomplete output blanking.') from exc


def item_by_id(conn, item_id):
    matches = [item for index in range(1, conn.timeline.GetTrackCount('video') + 1)
               for item in conn.timeline.GetItemListInTrack('video', index) or []
               if str(item.GetUniqueId()) == item_id and item.GetType() == 'video']
    if len(matches) != 1:
        raise ValidationError('Output blanking requires one exact video timeline item.')
    return matches[0]


def _read(conn, item=None):
    _require_api(conn)
    timeline = _native_edges(conn.timeline)
    if item is None:
        return {'blanking': timeline}
    inherit = item.GetUseTimelineForOutputBlanking()
    if not isinstance(inherit, bool):
        raise APICallFailed('DaVinci Resolve returned an invalid output blanking inheritance flag.')
    raw = item.GetOutputBlanking()
    if inherit:
        if raw != {}:
            raise APICallFailed('Inherited clip output blanking did not return the documented empty dictionary.')
        own = None
    else:
        own = _native_edges(item)
    return {'use_timeline': inherit, 'blanking': own, 'effective_blanking': timeline if inherit else own}


def read(conn, item=None):
    _require_api(conn)
    with _preserve_render_context(conn):
        return _read(conn, item)


def _set_edges(target, value):
    if target.SetOutputBlanking({key.title(): number for key, number in value.items()}) is not True:
        raise APICallFailed('DaVinci Resolve rejected output blanking.')
    if _native_edges(target) != value:
        raise APICallFailed('DaVinci Resolve output blanking readback differs from the request.')


def _inherit(item, value):
    if item.SetUseTimelineForOutputBlanking(value) is not True or item.GetUseTimelineForOutputBlanking() is not value:
        raise APICallFailed('DaVinci Resolve did not verify output blanking inheritance.')


def write(conn, value=None, *, item=None, use_timeline=None):
    _require_api(conn)
    if item is None and use_timeline is not None:
        raise ValidationError('Only a clip can inherit timeline output blanking.')
    if value is not None:
        value = edges(value)
    if (value is None) == (use_timeline is None):
        raise ValidationError('Specify either all four blanking edges or clip inheritance.')
    if use_timeline is not None and not isinstance(use_timeline, bool):
        raise ValidationError('Output blanking inheritance must be boolean.')
    with _preserve_render_context(conn):
        before = _read(conn, item)
        desired = {'blanking': value} if item is None else None
        if desired == before or (item is not None and use_timeline == before['use_timeline'] and value is None):
            return {'before': before, 'after': before, 'changed': False}
        target = item or conn.timeline
        saved_own = before['blanking']
        timeline_ops.require_sdk_marker_mutation_guard(conn)
        try:
            if item is None:
                _set_edges(target, value)
            elif value is None:
                _inherit(item, use_timeline)
            else:
                if before['use_timeline']:
                    # Capture the hidden override before replacing it, for exact rollback.
                    _inherit(item, False)
                    saved_own = _native_edges(item)
                _set_edges(item, value)
            after = _read(conn, item)
            if value is not None and (after['blanking'] != value or after.get('use_timeline', False)):
                raise APICallFailed('DaVinci Resolve did not apply the requested output blanking override.')
            return {'before': before, 'after': after, 'changed': after != before}
        except Exception as exc:
            restored = False
            try:
                if item is None:
                    _set_edges(target, before['blanking'])
                else:
                    if saved_own is not None:
                        _inherit(item, False)
                        _set_edges(item, saved_own)
                    _inherit(item, before['use_timeline'])
                restored = _read(conn, item) == before
            except Exception:
                pass
            raise APICallFailed('Output blanking failed; inspect the recorded restoration result.',
                                details={'restoration_verified': restored, 'before': before}) from exc


def snapshot(conn):
    """Private revision evidence; inherited clips retain their explicit inheritance flag."""
    if not resolve_api_version.at_least(conn, 21, 1):
        return None
    with _preserve_render_context(conn):
        items = {}
        for index in range(1, conn.timeline.GetTrackCount('video') + 1):
            for item in conn.timeline.GetItemListInTrack('video', index) or []:
                if item.GetType() != 'video':
                    continue
                try:
                    state = _read(conn, item)
                except APICallFailed:
                    # Generators/titles can expose a video type without clip blanking.
                    # Keep that observation explicit without breaking the entire snapshot.
                    state = {'available': False, 'reason': 'clip_output_blanking_unavailable'}
                items[str(item.GetUniqueId())] = state
        return {'timeline': _read(conn), 'items': items}
