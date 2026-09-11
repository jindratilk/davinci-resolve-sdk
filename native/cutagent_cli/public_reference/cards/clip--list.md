# `clip list`

Syntax: `cutagent clip list [--track-type VALUE] [--track VALUE]`

## Search terms

- list timeline clips on track
- show items on video track
- inspect audio track contents
- enumerate subtitle clips
- get clip start end duration
- find duplicate names on a track
- check whether a timeline track is empty
- inventory one timeline layer

## What it does

List clips on a track.

## Do not use when

Use `clip current` when only the playhead item matters. Do not interpret this as a whole-timeline inventory unless every track type/index has been queried.

## Preflight and readback

Query each relevant track separately and retain type/index alongside the returned rows because rows themselves do not contain either. If names repeat, use start/end plus a selector-capable command's `--at`/track options before mutation.

## Public arguments and options

- `--track-type` (optional, default: `"video"`) — Track type: video, audio, subtitle
- `--track` (optional, default: `1`) — Track index

## Boundaries and gotchas

- Track index is one-based.
- Only `video`, `audio`, and `subtitle` are accepted.
- Duplicate names can be indistinguishable without start/end context.
- Do not confuse that with an out-of-range track, which is an error.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent clip list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
