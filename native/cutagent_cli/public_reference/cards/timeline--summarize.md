# `timeline summarize`

Syntax: `cutagent timeline summarize [--window VALUE] [--radius VALUE] [--from VALUE] [--to VALUE] [--track-type VALUE] [--max-runs VALUE] [--include-items]`

## Search terms

- summarize current timeline
- editor-readable timeline map
- timeline source runs
- playhead window summary
- multicam angle map
- timeline readiness hints
- compact track overview
- inspect timeline around playhead

## What it does

Summarize the current timeline as an editor-readable map.

## Do not use when

Do not treat the readiness/angle/pattern fields as authoritative editorial analysis. They are simple name/source/count heuristics and explicitly do not prove picture lock, transcription safety, caption safety, or multicam semantics.

## Preflight and readback

Use `--include-items` only when individual rows are needed.
After execution, inspect window bounds/playhead, track counts, truncation flags, source identity, and items at playhead. Corroborate heuristic patterns/readiness with DaVinci Resolve and narrower item/track commands before editing, transcribing, captioning, or declaring picture lock.

## Public arguments and options

- `--window` (optional, default: `"current"`) — Summary window: current (around playhead), all, or range. --from/--to imply range. Use --window all only when the full-timeline map is really needed; it can be very large.
- `--radius` (optional, default: `"30s"`) — Radius around the playhead for --window current, for example 30s or 720f.
- `--from` (optional) — Record-domain range start: timecode, seconds, or frames.
- `--to` (optional) — Record-domain range end: timecode, seconds, or frames.
- `--track-type` (optional, default: `"all"`) — Track type to summarize: all, video, audio, or subtitle.
- `--max-runs` (optional, default: `24`) — Maximum source runs to include per track.
- `--include-items` (optional, default: `false`) — Include compact per-item rows for the summarized window.

## Boundaries and gotchas

- Allowed windows are `current`, `all`, and `range`, case/whitespace normalized.
- Supplying either `--from` or `--to` forces range mode regardless of `--window`.
- Range mode requires both endpoints.
- Explicit range end must resolve strictly after start.
- `--window current` parses `--radius`, default `30s`.
- Radius accepts shared duration forms such as seconds, timecode, or frames and must resolve nonnegative.
- Current range start is clamped to timeline start.
- Current range end is `playhead + radius + 1`, supporting half-open inclusion of the playhead endpoint.
- `--window all` ignores radius completely, even if radius text is invalid.
- `--from`/`--to` are record-domain refs.
- `--max-runs` defaults to 24 and must be an integer at least 1.
- `--include-items` defaults false.
- A video-only summary can therefore still query item counts on audio/subtitle tracks.
- Heuristics can add notes about missing audio/subtitles or apparent multicam switches; they do not inspect actual downstream workflows.
- Global dry-run has no alternate path and still connects/reads.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent timeline summarize --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
