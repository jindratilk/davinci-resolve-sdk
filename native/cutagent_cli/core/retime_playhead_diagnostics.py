"""Bounded in-memory evidence for private retime failure diagnostics."""
from contextlib import contextmanager
from contextvars import ContextVar
import math

_active = ContextVar("retime_playhead_diagnostics", default=None)
_NUMBERS = ("target_frame", "pre_frame", "actual_frame", "final_frame")
_TIMECODES = ("target_tc", "pre_tc", "actual_tc", "final_tc")


def _fields(value):
    if not isinstance(value, dict):
        return {}
    result = {key: value[key] for key in _NUMBERS
              if type(value.get(key)) in (int, float) and abs(value[key]) <= 2**53 - 1
              and math.isfinite(value[key])}
    for key in _TIMECODES:
        text = value.get(key)
        if isinstance(text, str) and len(text) <= 32 and all(c in "0123456789:;." for c in text):
            result[key] = text
    if type(value.get("api_result")) is bool:
        result["api_result"] = value["api_result"]
    return result


@contextmanager
def reference_diagnostics():
    state = {"moves": [], "move_count": 0}
    token = _active.set(state)
    try:
        yield
    except Exception as failure:
        # An exception attribute is private; never add it to the CLI envelope.
        failure.retime_playhead_diagnostic = state
        raise
    finally:
        _active.reset(token)


def move_playhead(move, conn, position, *, restoring=False):
    state = _active.get()
    if state is None:
        return move(conn, position, return_details=True, frame_tolerance=0)
    event = {"restore": restoring}
    state["move_count"] += 1
    state["moves"].append(event)
    del state["moves"][:-16]
    try:
        result = move(conn, position, return_details=True, frame_tolerance=0)
        event.update(_fields(result))
        event["ok"] = True
        return result
    except Exception as failure:
        event.update(_fields(getattr(failure, "details", None)))
        event["ok"] = False
        state["failure"] = dict(event)
        raise
