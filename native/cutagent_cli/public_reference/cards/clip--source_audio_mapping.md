# `clip source-audio-mapping`

Syntax: `cutagent clip source-audio-mapping [CLIP]`

## Search terms

- inspect clip audio channel mapping
- see which source channels feed timeline item
- check mono stereo source mapping
- get embedded audio channel count
- diagnose missing clip audio
- inspect linked audio mapping JSON
- verify timeline item channel assignment
- source audio routing readback

## What it does

Check source audio channel mapping for a timeline item.

## Do not use when

Use media/source audio mapping mutation commands to change channel interpretation, Fairlight routing commands for track/bus flow, and `clip linked list` for timeline-item link relationships. Use `media audio-mapping` when the Media Pool item's source mapping rather than one timeline occurrence is the target.

## Preflight and readback

Resolve the exact item and identify whether it is video, audio, or multicam. Compare it with Media Pool audio mapping, track format, and an actual playback/render.

## Public arguments and options

- `CLIP` (optional) — Clip name (current clip when omitted)

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent clip source-audio-mapping --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
