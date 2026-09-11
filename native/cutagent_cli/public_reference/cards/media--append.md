# `media append`

Syntax: `cutagent media append NAME [--at VALUE] [--timeline VALUE] [--track-type VALUE] [--track VALUE] [--source-start VALUE] [--source-end VALUE] [--record-frame VALUE] [--absolute-record-frame VALUE]`

## Search terms

- append Media Pool clip to timeline
- place clip at record frame
- add audio to timeline track
- put footage on a named timeline
- append clip in and out range
- add music at one second
- place audio without video
- add clip to V1 or A1

## What it does

Append media to the timeline.

## Preflight and readback

Resolve the Media Pool identity with exact search and inspect the target timeline's start frame, existing tracks, and occupancy using `timeline track items`.

## Public arguments and options

- `NAME` (required) — Clip name
- `--at` (optional) — Record-domain position; legacy alias for --record-frame
- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--track-type` (optional, default: `"video"`) — Track type: video or audio
- `--track/--track-index` (optional, default: `1`) — Timeline track index
- `--source-start/--start-frame` (optional) — Source-domain startFrame
- `--source-end/--end-frame` (optional) — Source-domain endFrame
- `--record-frame` (optional) — Record-domain recordFrame
- `--absolute-record-frame` (optional) — Exact DaVinci Resolve API recordFrame; no timeline-start offset is applied

## Boundaries and gotchas

- Only `video` and `audio` track types are accepted, and the track index must be at least 1.
- The command does not add a missing track or preflight that the requested index exists.
- `--at`, `--record-frame`, and `--absolute-record-frame` are mutually exclusive.
- End must be greater than start and, when DaVinci Resolve exposes a usable duration property, both are checked against the source length.
- One current-folder duplicate silently resolves to the first; multiple recursive matches outside it raise an ambiguity error.
- Audio-only placement adds `mediaType: 2`.
- Requesting `--track-type video` for an audio-only asset can fail or produce no useful placement; choose the stream/track domain that exists.

## Examples

- `cutagent media append --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
