# `timeline subtitle list`

Syntax: `cutagent timeline subtitle list [--track VALUE]`

## Search terms

- list timeline subtitles
- inspect subtitle track items
- subtitle clip timecodes
- enumerate caption tracks
- subtitle frame bounds

## What it does

List subtitle clips.

## Do not use when

Do not assume empty text or zero-length/zero-frame rows reflect real item state.

## Preflight and readback

Before execution, activate the exact timeline, confirm FPS/start frame, and choose an existing positive subtitle track when narrowing scope.
After execution, verify track/start/end/text against DaVinci Resolve, especially rows with empty text, start 0, end equal start, or clamped `00:00:00:00`. Use frame fields as primary evidence and remember multi-track output is grouped by track, not globally chronological.

## Public arguments and options

- `--track` (optional) — Subtitle track index

## Boundaries and gotchas

- `--track` is optional.
- When track is supplied, only that exact integer is queried.
- Global dry-run has no special branch and still connects/reads.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent timeline subtitle list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
