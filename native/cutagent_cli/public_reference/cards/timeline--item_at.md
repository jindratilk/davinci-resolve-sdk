# `timeline item-at`

Syntax: `cutagent timeline item-at POSITION [--track-type VALUE] [--track VALUE]`

## Search terms

- timeline item at position
- clips covering record frame
- item under timeline time
- inspect all tracks at frame
- video audio subtitle overlap
- half-open timeline item range

## What it does

Find timeline item(s) at a position.

## Do not use when

Do not use this command with an absolute displayed timeline timecode unless it has first been converted to a timeline-relative record offset.
Do not use it to identify selected/current UI items, media-pool identity, linked groups, or every item merely touching a boundary.

## Preflight and readback

Before execution, inspect timeline FPS/start frame and convert the intended point to a relative record-domain reference. Validate track type and use a positive existing track index when narrowing scope.
After execution, confirm the resolved `position`, track type/index, and item bounds.

## Public arguments and options

- `POSITION` (required) — Record-domain position
- `--track-type` (optional, default: `"all"`) — video, audio, subtitle, or all
- `--track` (optional) — Track index

## Boundaries and gotchas

- `--track` is optional and parsed as an integer.
- The command does not require `--track` to be at least 1.
- With `--track` and `all`, the same numeric index is queried for video, audio, and subtitle.
- Output does not include timecodes, track names, item ids, media-pool objects, source bounds, file paths, links, enabled state, or clip properties.
- `--dry-run` has no special branch and still connects/reads.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline item-at --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
