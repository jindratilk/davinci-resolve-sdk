"""Agent output mode — compact text rendering of contract envelopes for LLM consumption.

The agent mode exists to keep relevant-context-per-token high for the CutAgent
runtime: one-line meta, timecodes over duplicated frame counts, source aliases
instead of repeated long names, no pretty-printed JSON, and spill-to-disk with
an actionable pointer instead of flooding the model context with huge payloads.

The machine contract (`--json`) is unchanged; agent mode is a rendering of the
same envelopes, so every success/error path shares one code path with JSON.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Sequence

AGENT_MAX_CHARS_DEFAULT = 12_000
_AGENT_MIN_MAX_CHARS = 2_000
_HEAD_RATIO = 0.65
_MAX_CELL_WIDTH = 48

# Meta fields that only earn a place on the meta line when they deviate from
# their resting defaults.
_META_DEFAULTS = {
    "verification_status": "not_requested",
    "recoverability": "not_applicable",
    "policy_profile": "auto_edit",
    "capability_status": "supported",
}


def agent_max_chars() -> int:
    raw = os.environ.get("CUTAGENT_CLI_AGENT_MAX_CHARS")
    try:
        value = int(raw) if raw else AGENT_MAX_CHARS_DEFAULT
    except (TypeError, ValueError):
        value = AGENT_MAX_CHARS_DEFAULT
    return max(_AGENT_MIN_MAX_CHARS, value)


def _spill_dir() -> Path:
    configured = os.environ.get("CUTAGENT_CLI_SPILL_DIR")
    base = Path(configured) if configured else Path(tempfile.gettempdir()) / "cutagent-agent-output"
    base.mkdir(parents=True, exist_ok=True)
    return base


def maybe_spill(text: str, command: str | None) -> str:
    """Spill oversized agent output to disk, returning head+tail with a pointer.

    The truncation message is actionable on purpose: it names the exact file
    with the full output and the narrowing flags to re-run with.
    """
    limit = agent_max_chars()
    if len(text) <= limit:
        return text

    slug = re.sub(r"[^a-z0-9._-]+", "-", (command or "output").lower()).strip("-") or "output"
    spill_path: Path | None = None
    try:
        spill_path = _spill_dir() / f"{slug}-{int(time.time() * 1000)}.txt"
        spill_path.write_text(text, encoding="utf-8")
    except OSError:
        spill_path = None

    head_budget = int(limit * _HEAD_RATIO)
    tail_budget = max(limit - head_budget - 400, 500)
    head = text[:head_budget]
    cut = head.rfind("\n")
    if cut > head_budget // 2:
        head = head[:cut]
    tail = text[-tail_budget:]
    cut = tail.find("\n")
    if 0 <= cut < tail_budget // 2:
        tail = tail[cut + 1 :]

    if spill_path is not None:
        pointer = f"Full output saved to: {spill_path} — Read or grep that file"
    else:
        pointer = "Full output could not be saved to disk"
    marker = (
        f"\n[... TRUNCATED: output was {len(text)} chars ({len(text) - len(head) - len(tail)} omitted). "
        f"{pointer}, or re-run with narrowing flags such as --select, --window current, "
        f"--track-type, or --max-runs. ...]\n"
    )
    return head + marker + tail


def _fmt_scalar(value: Any) -> str:
    if value is None:
        return ""
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _clip_cell(text: str) -> str:
    if len(text) <= _MAX_CELL_WIDTH:
        return text
    return text[: _MAX_CELL_WIDTH - 1] + "…"


def _render_table(rows: Sequence[dict], columns: list[tuple[str, str]] | None) -> list[str]:
    if not rows:
        return ["(none)"]
    if columns:
        keys = [key for key, _header in columns]
    else:
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
    # Drop columns that are empty in every row — nulls cost tokens, not insight.
    keys = [
        key
        for key in keys
        if any(row.get(key) not in (None, "", [], {}) for row in rows)
    ]
    if not keys:
        return ["(none)"]

    def cell(row: dict, key: str) -> str:
        value = row.get(key)
        if _is_scalar(value):
            return _clip_cell(_fmt_scalar(value))
        return _clip_cell(str(value))

    widths = {key: len(key) for key in keys}
    rendered_rows = []
    for row in rows:
        rendered = {key: cell(row, key) for key in keys}
        rendered_rows.append(rendered)
        for key in keys:
            widths[key] = max(widths[key], len(rendered[key]))

    lines = ["  ".join(key.ljust(widths[key]) for key in keys).rstrip()]
    for rendered in rendered_rows:
        lines.append("  ".join(rendered[key].ljust(widths[key]) for key in keys).rstrip())
    return lines


def _render_value(value: Any, indent: int = 0) -> list[str]:
    pad = "  " * indent
    if _is_scalar(value):
        return [f"{pad}{_fmt_scalar(value)}"]

    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if item is None or item == {} or item == []:
                continue
            if _is_scalar(item):
                lines.append(f"{pad}{key}: {_fmt_scalar(item)}")
            elif isinstance(item, list) and item and all(isinstance(row, dict) for row in item):
                lines.append(f"{pad}{key} ({len(item)}):")
                lines.extend("  " * (indent + 1) + line for line in _render_table(item, None))
            elif isinstance(item, list) and all(_is_scalar(entry) for entry in item):
                joined = ", ".join(_fmt_scalar(entry) for entry in item)
                if len(joined) <= 100:
                    lines.append(f"{pad}{key}: {joined}")
                else:
                    lines.append(f"{pad}{key}:")
                    lines.extend(f"{pad}  - {_fmt_scalar(entry)}" for entry in item)
            else:
                lines.append(f"{pad}{key}:")
                lines.extend(_render_value(item, indent + 1))
        return lines or [f"{pad}(empty)"]

    if isinstance(value, list):
        if not value:
            return [f"{pad}(none)"]
        if all(isinstance(row, dict) for row in value):
            return [pad + line for line in _render_table(value, None)]
        return [f"{pad}- {_fmt_scalar(item) if _is_scalar(item) else item}" for item in value]

    return [f"{pad}{value}"]


def _meta_line(meta: dict[str, Any], *, ok: bool) -> str:
    parts = [meta.get("command") or "cutagent"]
    engine = meta.get("engine")
    if engine:
        parts.append(str(engine))
    duration = meta.get("duration_ms")
    if isinstance(duration, (int, float)):
        parts.append(f"{int(duration)}ms")
    if meta.get("dry_run"):
        parts.append("dry-run")
    for key in ("verification_status", "recoverability", "policy_profile", "capability_status"):
        value = meta.get(key)
        if value and value != _META_DEFAULTS.get(key):
            parts.append(f"{key.replace('_', ' ')}: {value}")
    rollback = meta.get("rollback_hint")
    if rollback:
        parts.append(f"rollback: {rollback}")
    prefix = "# ok" if ok else "# ERROR"
    return f"{prefix} · " + " · ".join(str(part) for part in parts)


# --- Command-specific compact renderers -------------------------------------


def _source_alias_map(tracks: Sequence[dict]) -> dict[str, str]:
    """Assign short aliases (S1, S2, …) to source names that repeat in runs."""
    order: list[str] = []
    for track in tracks:
        for run in track.get("runs") or []:
            source = run.get("source")
            if source and source not in order:
                order.append(source)
        for item in track.get("items_at_playhead") or []:
            source = item.get("source")
            if source and source not in order:
                order.append(source)
    return {source: f"S{index + 1}" for index, source in enumerate(order)}


def _run_label(run: dict, aliases: dict[str, str]) -> str:
    angle = run.get("angle")
    source = run.get("source")
    alias = aliases.get(source, "") if source else ""
    if angle is not None and alias:
        return f"{alias}/A{angle}"
    if angle is not None:
        return f"A{angle}"
    if alias:
        return alias
    label = run.get("label") or run.get("source") or "?"
    return _clip_cell(str(label))


def _render_summarize(data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    timeline = data.get("timeline") or {}
    if timeline:
        resolution = timeline.get("resolution") or {}
        res = ""
        if resolution.get("width") and resolution.get("height"):
            res = f" · {resolution['width']}x{resolution['height']}"
        lines.append(
            f"timeline \"{timeline.get('name', '?')}\" · {_fmt_scalar(timeline.get('fps'))}fps"
            f" · {timeline.get('duration', '?')}"
            f" · {timeline.get('video_tracks', 0)}V/{timeline.get('audio_tracks', 0)}A/{timeline.get('subtitle_tracks', 0)}S{res}"
        )
    window = data.get("window") or {}
    if window:
        playhead = (window.get("playhead") or {}).get("timecode")
        window_desc = window.get("mode", "all")
        if window.get("start_timecode") and window.get("end_timecode"):
            window_desc += f" {window['start_timecode']}–{window['end_timecode']}"
        elif window.get("mode") == "current":
            window_desc += f" ±{window.get('radius', '')}"
        line = f"window {window_desc}"
        if playhead:
            line += f" · playhead {playhead}"
        lines.append(line)

    tracks = data.get("tracks") or []
    aliases = _source_alias_map(tracks)
    if aliases:
        lines.append("sources:")
        lines.extend(f"  {alias} = \"{source}\"" for source, alias in aliases.items())

    for track in tracks:
        track_type = str(track.get("type", "?"))
        prefix = {"video": "V", "audio": "A", "subtitle": "ST"}.get(track_type, track_type)
        header = f"{prefix}{track.get('index', '?')} \"{track.get('name', '')}\""
        total = track.get("total_item_count")
        in_window = track.get("window_item_count")
        if total is not None:
            header += f" · {total} items" if in_window in (None, total) else f" · {in_window}/{total} items in window"
        pattern = track.get("pattern")
        if pattern:
            header += f" · {pattern}"
        if str(track.get("enabled", "✓")) not in ("✓", "yes", "True", "true"):
            header += " · disabled"
        if str(track.get("locked", "")) in ("✓", "yes", "True", "true"):
            header += " · locked"
        lines.append(header)

        for item in track.get("items_at_playhead") or []:
            label = _run_label(item, aliases) if item.get("source") in aliases else _clip_cell(str(item.get("name", "?")))
            item_id = item.get("timeline_item_id")
            id_part = f" · id {item_id}" if item_id else ""
            lines.append(
                f"  @playhead {label} {item.get('start_timecode', '?')}–{item.get('end_timecode', '?')}{id_part}"
            )

        runs = track.get("runs") or []
        if runs:
            entries = [f"{run.get('start_timecode', '?')} {_run_label(run, aliases)}" for run in runs]
            last_end = runs[-1].get("end_timecode")
            if last_end:
                entries.append(f"end {last_end}")
            # Wrap the run map at ~100 chars per line to stay grep-friendly.
            lines.append("  runs: " + " | ".join(entries[:8]))
            for start in range(8, len(entries), 8):
                lines.append("        " + " | ".join(entries[start : start + 8]))
        if track.get("runs_truncated"):
            lines.append(
                f"  (+more runs truncated at --max-runs {track.get('max_runs')}; run_count {track.get('run_count')})"
            )

        items = track.get("items")
        if isinstance(items, list) and items:
            lines.append(f"  items ({len(items)}):")
            lines.extend("  " + line for line in _render_table(items, None))

    for key in ("subtitles", "transcript", "captions", "notes"):
        extra = data.get(key)
        if extra:
            lines.append(f"{key}:")
            lines.extend(_render_value(extra, 1))
    return lines


def _render_capabilities(data: dict[str, Any]) -> list[str]:
    graph = data.get("feature_graph")
    if not isinstance(graph, dict) or not graph:
        return _render_value(data)

    domains: dict[str, dict[str, int]] = {}
    status_totals: dict[str, int] = {}
    for feature_id, feature in graph.items():
        status = str((feature or {}).get("status", "unknown"))
        domain = str(feature_id).split(".", 1)[0]
        domains.setdefault(domain, {})
        domains[domain][status] = domains[domain].get(status, 0) + 1
        status_totals[status] = status_totals.get(status, 0) + 1

    lines = [
        f"{len(graph)} features · "
        + " · ".join(f"{status} {count}" for status, count in sorted(status_totals.items(), key=lambda kv: -kv[1]))
    ]
    transport = data.get("transport")
    if transport:
        lines.append(f"transport: {transport}")
    lines.append("domains:")
    for domain in sorted(domains):
        counts = domains[domain]
        total = sum(counts.values())
        non_supported = {status: count for status, count in counts.items() if status != "supported"}
        detail = ""
        if non_supported:
            detail = " (" + ", ".join(f"{count} {status}" for status, count in sorted(non_supported.items())) + ")"
        lines.append(f"  {domain}: {total}{detail}")
    lines.append(
        "Use `capabilities <feature_id>` for one feature or `capabilities --full --json` for the complete graph."
    )
    return lines


_COMMAND_RENDERERS: dict[str, Callable[[dict[str, Any]], list[str]]] = {
    "timeline.summarize": _render_summarize,
    "capabilities": _render_capabilities,
}


def render_envelope(
    envelope: dict[str, Any],
    columns: list[tuple[str, str]] | None = None,
) -> str:
    """Render a contract envelope as compact agent-facing text."""
    meta = envelope.get("meta") or {}
    ok = bool(envelope.get("ok"))
    lines = [_meta_line(meta, ok=ok)]

    if not ok:
        error = envelope.get("error") or {}
        code = error.get("code", "INTERNAL_ERROR")
        lines.append(f"{code}: {error.get('message', 'Unknown error.')}")
        fix = error.get("suggested_fix")
        if fix:
            lines.append(f"fix: {fix}")
        details = error.get("details")
        if isinstance(details, dict) and details:
            lines.append("details:")
            lines.extend(_render_value(details, 1))
        return "\n".join(lines)

    data = envelope.get("data")
    command = str(meta.get("command") or "")
    renderer = _COMMAND_RENDERERS.get(command)
    body: list[str] | None = None
    if renderer is not None and isinstance(data, dict):
        try:
            body = renderer(data)
        except Exception:
            body = None
    if body is None:
        if data is None:
            body = []
        elif isinstance(data, list) and data and all(isinstance(row, dict) for row in data):
            body = _render_table(data, columns)
        else:
            body = _render_value(data)
    lines.extend(body)
    return "\n".join(lines)
