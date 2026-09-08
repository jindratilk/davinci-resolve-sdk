"""EDL parsing, manipulation, and writing for ripple edit workaround."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from ..utils.timecode import timecode_to_seconds, seconds_to_timecode


@dataclass
class EDLEvent:
    """A single EDL event (edit decision)."""
    number: int
    reel: str
    track_type: str  # e.g. "V", "A", "A2"
    edit_type: str   # e.g. "C" (cut), "D" (dissolve)
    source_in: str   # timecode HH:MM:SS:FF
    source_out: str
    record_in: str
    record_out: str
    transition_duration: str = ""
    clip_name: str = ""
    comments: List[str] = field(default_factory=list)
    fps: float = 25.0

    @property
    def record_in_seconds(self) -> float:
        return timecode_to_seconds(self.record_in, self.fps)

    @property
    def record_out_seconds(self) -> float:
        return timecode_to_seconds(self.record_out, self.fps)

    @property
    def duration_seconds(self) -> float:
        return self.record_out_seconds - self.record_in_seconds

    @property
    def source_duration_seconds(self) -> float:
        return timecode_to_seconds(self.source_out, self.fps) - timecode_to_seconds(
            self.source_in, self.fps
        )


def parse_edl(path: str, fps: float = 25.0) -> List[EDLEvent]:
    """
    Parse a CMX 3600-style EDL file into a list of EDLEvent objects.

    Args:
        path: Path to the EDL file.
        fps: Frames per second for timecode parsing.

    Returns:
        List of EDLEvent objects.
    """
    events: List[EDLEvent] = []
    # Standard EDL line: 001  REEL  V  C  01:00:00:00 01:00:05:00 01:00:00:00 01:00:05:00
    event_re = re.compile(
        r"^\s*(\d{3,})\s+"       # event number
        r"(\S+)\s+"              # reel name
        r"(\S+)\s+"              # track type (V, A, A2, AA, etc.)
        r"(\S+)\s+"              # edit type (C, D, W, K)
        r"(?:(\d{1,3})\s+)?"     # optional transition duration (e.g. D 012)
        r"(\d{2}:\d{2}:\d{2}[;:]\d{2})\s+"  # source in
        r"(\d{2}:\d{2}:\d{2}[;:]\d{2})\s+"  # source out
        r"(\d{2}:\d{2}:\d{2}[;:]\d{2})\s+"  # record in
        r"(\d{2}:\d{2}:\d{2}[;:]\d{2})"     # record out
    )

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    current_event: Optional[EDLEvent] = None

    for line in lines:
        line = line.rstrip("\n\r")

        m = event_re.match(line)
        if m:
            current_event = EDLEvent(
                number=int(m.group(1)),
                reel=m.group(2),
                track_type=m.group(3),
                edit_type=m.group(4),
                transition_duration=m.group(5) or "",
                source_in=m.group(6),
                source_out=m.group(7),
                record_in=m.group(8),
                record_out=m.group(9),
                fps=fps,
            )
            events.append(current_event)
            continue

        # Clip name from comments
        if current_event and line.startswith("* FROM CLIP NAME:"):
            current_event.clip_name = line.split(":", 1)[1].strip()
        elif current_event and line.startswith("*"):
            current_event.comments.append(line)

    return events


def remove_segment(
    events: List[EDLEvent],
    start_tc: str,
    duration_seconds: float,
    fps: float = 25.0,
) -> List[EDLEvent]:
    """
    Remove a time segment from the EDL and close the gap (ripple delete).

    Args:
        events: List of EDLEvent objects.
        start_tc: Start timecode of the segment to remove.
        duration_seconds: Duration to remove in seconds.
        fps: Frames per second.

    Returns:
        New list of EDLEvent objects with the segment removed and gap closed.
    """
    cut_start = timecode_to_seconds(start_tc, fps)
    cut_end = cut_start + duration_seconds

    result: List[EDLEvent] = []
    offset = 0.0  # accumulated time shift for ripple

    for evt in events:
        rec_in = evt.record_in_seconds
        rec_out = evt.record_out_seconds

        # Case 1: Event entirely before the cut — keep as-is (with offset)
        if rec_out <= cut_start:
            new_evt = _shift_event(evt, -offset, fps)
            result.append(new_evt)
            continue

        # Case 2: Event entirely within the cut — remove it
        if rec_in >= cut_start and rec_out <= cut_end:
            offset += (rec_out - rec_in)
            continue

        # Case 3: Event entirely after the cut — shift by cut duration
        if rec_in >= cut_end:
            new_evt = _shift_event(evt, -(cut_end - cut_start + offset - (cut_end - cut_start)), fps)
            # Simplify: shift by total accumulated offset
            new_evt = _shift_event(evt, -(cut_end - cut_start), fps)
            result.append(new_evt)
            continue

        # Case 4: Cut starts inside this event — split/trim
        if rec_in < cut_start and rec_out > cut_start:
            if rec_out <= cut_end:
                # Trim tail: keep [rec_in, cut_start]
                trim_amount = rec_out - cut_start
                new_evt = _trim_event_tail(evt, cut_start, fps)
                offset += trim_amount
                result.append(new_evt)
            else:
                # Cut is entirely within this event — split into two parts
                # Part 1: [rec_in, cut_start]
                part1 = _trim_event_tail(evt, cut_start, fps)
                result.append(part1)

                # Part 2: [cut_end, rec_out] — shifted back
                part2 = _trim_event_head_and_shift(evt, cut_end, cut_end - cut_start, fps)
                result.append(part2)
            continue

        # Case 5: Cut ends inside this event — trim head
        if rec_in >= cut_start and rec_in < cut_end and rec_out > cut_end:
            trim_amount = cut_end - rec_in
            new_evt = _trim_event_head_and_shift(evt, cut_end, cut_end - cut_start, fps)
            result.append(new_evt)
            continue

    # Renumber events
    for i, evt in enumerate(result, 1):
        evt.number = i

    return result


def _shift_event(evt: EDLEvent, shift_seconds: float, fps: float) -> EDLEvent:
    """Create a copy of the event with record times shifted."""
    new_rec_in = max(0, evt.record_in_seconds + shift_seconds)
    new_rec_out = max(0, evt.record_out_seconds + shift_seconds)
    return EDLEvent(
        number=evt.number,
        reel=evt.reel,
        track_type=evt.track_type,
        edit_type=evt.edit_type,
        transition_duration=evt.transition_duration,
        source_in=evt.source_in,
        source_out=evt.source_out,
        record_in=seconds_to_timecode(new_rec_in, fps),
        record_out=seconds_to_timecode(new_rec_out, fps),
        clip_name=evt.clip_name,
        comments=list(evt.comments),
        fps=fps,
    )


def _trim_event_tail(evt: EDLEvent, new_record_out_seconds: float, fps: float) -> EDLEvent:
    """Trim the tail of an event (keep start, shorten end)."""
    new_duration = new_record_out_seconds - evt.record_in_seconds
    # Adjust source out proportionally
    src_in = timecode_to_seconds(evt.source_in, fps)
    new_src_out = src_in + new_duration

    return EDLEvent(
        number=evt.number,
        reel=evt.reel,
        track_type=evt.track_type,
        edit_type=evt.edit_type,
        transition_duration=evt.transition_duration,
        source_in=evt.source_in,
        source_out=seconds_to_timecode(new_src_out, fps),
        record_in=evt.record_in,
        record_out=seconds_to_timecode(new_record_out_seconds, fps),
        clip_name=evt.clip_name,
        comments=list(evt.comments),
        fps=fps,
    )


def _trim_event_head_and_shift(
    evt: EDLEvent,
    new_record_in_seconds: float,
    shift_seconds: float,
    fps: float,
) -> EDLEvent:
    """Trim the head of an event and shift record times back (ripple)."""
    # How much we're trimming from the head
    head_trim = new_record_in_seconds - evt.record_in_seconds
    src_in = timecode_to_seconds(evt.source_in, fps) + head_trim
    src_out = timecode_to_seconds(evt.source_out, fps)  # source out stays

    # New record positions (shifted back by the cut duration)
    new_rec_in = new_record_in_seconds - shift_seconds
    new_rec_out = evt.record_out_seconds - shift_seconds

    return EDLEvent(
        number=evt.number,
        reel=evt.reel,
        track_type=evt.track_type,
        edit_type=evt.edit_type,
        transition_duration=evt.transition_duration,
        source_in=seconds_to_timecode(src_in, fps),
        source_out=seconds_to_timecode(src_out, fps),
        record_in=seconds_to_timecode(new_rec_in, fps),
        record_out=seconds_to_timecode(new_rec_out, fps),
        clip_name=evt.clip_name,
        comments=list(evt.comments),
        fps=fps,
    )


def write_edl(
    events: List[EDLEvent],
    output_path: str,
    title: str = "cutagent ripple edit",
) -> str:
    """
    Write EDL events to a CMX 3600-style EDL file.

    Args:
        events: List of EDLEvent objects.
        output_path: Output file path.
        title: EDL title.

    Returns:
        The output path.
    """
    lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]

    for evt in events:
        transition_fragment = f"{evt.transition_duration:>3s} " if evt.transition_duration else "    "
        # Standard EDL line
        line = (
            f"{evt.number:03d}  {evt.reel:<8s} {evt.track_type:<5s} "
            f"{evt.edit_type:<4s} {transition_fragment}"
            f"{evt.source_in} {evt.source_out} "
            f"{evt.record_in} {evt.record_out}  "
        )
        lines.append(line)

        if evt.clip_name:
            lines.append(f"* FROM CLIP NAME: {evt.clip_name}")

        for comment in evt.comments:
            lines.append(comment)

        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines) + "\r\n")

    return output_path
