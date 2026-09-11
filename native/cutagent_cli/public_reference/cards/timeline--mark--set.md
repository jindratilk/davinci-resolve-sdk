# `timeline mark set`

Syntax: `cutagent timeline mark set --in VALUE --out VALUE [--type VALUE]`

## Search terms

- set timeline in and out
- define render range marks
- mark timeline section
- set video in out points
- set audio in out points
- choose timeline playback range
- set record-frame range
- create separate audio range
- limit timeline range with in out

## What it does

Set timeline mark in and out points.

## Do not use when

Do not use this to add a named or colored point marker; use the timeline marker-add command. Do not use it to set source trim points on a Media Pool clip (`media mark set`). If the intended range is expressed in timecode or seconds, translate it against the current timeline start and fps before calling this frame-only command.

## Preflight and readback

Convert the desired timecode bounds to absolute frames and ensure out is strictly greater than in. After setting, rerun `timeline mark get` and compare the selected category exactly; restore the previous video/audio ranges separately if the operation was temporary.

## Public arguments and options

- `--in` (required) — Mark-in frame
- `--out` (required) — Mark-out frame
- `--type` (optional, default: `"all"`) — all|video|audio

## Boundaries and gotchas

- `--in` and `--out` are absolute timeline frames, not offsets from timeline start.
- Setting one explicit category does not synchronize or erase the other.
- Verify with `timeline mark get`, especially before rendering or exporting a range.

## Examples

- `cutagent timeline mark set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
