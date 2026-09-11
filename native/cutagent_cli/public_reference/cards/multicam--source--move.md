# `multicam source move`

Syntax: `cutagent multicam source move --angle VALUE --item-index VALUE --record-start-frame VALUE [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--media-type VALUE]`

## Search terms

- multicam source move
- Move a source item inside a multicam angle.
- multicam source move help
- multicam source move command

## What it does

Move a source item inside a multicam angle.

## Do not use when

Do not create overlaps on the same angle; the command rejects them. Do not use a clip name when the intended target is an item index. Avoid video-only movement unless desynchronization is intentional.

## Preflight and readback

Inspect ordered items and gaps. After mutation require exact requested start, unchanged duration/source-in/media ID, paired video/audio timing, updated gap diagnostics, and reopen readback.

## Public arguments and options

- `--angle` (required)
- `--item-index` (required) — Zero-based source item index within the angle
- `--record-start-frame` (required) — New start relative to multicam start
- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--media-type` (optional, default: `"both"`) — both, video, or audio

## Boundaries and gotchas

- `--item-index` is zero-based; `--angle` is one-based.
- `--record-start-frame` is relative to multicam start.
- `--media-type` defaults to `both`.

## Examples

- `cutagent multicam source move --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
