# `edit trim`

Syntax: `cutagent edit trim [CLIP_NAME] [--head VALUE] [--tail VALUE] [--timeline VALUE] [--track VALUE] [--start-frame VALUE] [--current-end-frame VALUE] [--name VALUE] [--linked-audio VALUE]`

## Search terms

- trim the start of a clip
- trim the end of a clip
- shorten one video occurrence
- reject unsafe linked-audio preservation before mutation
- intentional video-only trim
- non-ripple head trim
- non-ripple tail trim

## What it does

Trim the head and tail of a clip.

## Do not use when

Use a ripple trim/roll operation when the user expects a gap to close or an adjacent edit point to move. Use `edit slip-selected` when the record span must stay fixed while source content moves. Use Fairlight clip trim for an audio-led target. Do not use this command when linked audio must remain linked. Use `--linked-audio exclude` only when the user explicitly accepts a video-only trim and possible link-topology change.

## Preflight and readback

Before running, identify the exact timeline and video occurrence. Run `--dry-run` with the final selector and trim values.
After success, consume the returned verification checks. For a production decision, also render or play the changed boundary to inspect the first/last retained source frames.

## Public arguments and options

- `CLIP_NAME` (optional) — Video item name selector
- `--head` (optional, default: `0.0`) — Trim from start (seconds)
- `--tail` (optional, default: `0.0`) — Trim from end (seconds)
- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--track/--track-index` (optional, default: `1`) — Video track index for selector
- `--start-frame` (optional) — Current video item start in record-domain frames/time
- `--current-end-frame` (optional) — Current video item end for stricter selection
- `--name` (optional) — Current timeline item name for stricter selection
- `--linked-audio` (optional, default: `"preserve"`)

## Boundaries and gotchas

- At least one of `--head` or `--tail` must be positive, each positive value must round to at least one frame, and their frame sum must leave at least one frame.
- `--head` and `--tail` are duration seconds, not record or source positions.
- `--start-frame` and `--current-end-frame` are record-domain selectors.
- A name-only selector is accepted only when exactly one item on the selected 1-based video track matches.
- `exclude` changes only video.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent edit trim --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
