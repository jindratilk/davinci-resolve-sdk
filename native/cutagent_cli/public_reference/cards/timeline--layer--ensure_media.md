# `timeline layer ensure-media`

Syntax: `cutagent timeline layer ensure-media --media VALUE [--timeline VALUE] --track VALUE --start-frame VALUE --duration VALUE [--extend-gap VALUE] [--match-name VALUE] [--allow-insert] [--allow-extend] [--dry-run]`

## Search terms

- ensure timeline media layer
- fill video track range
- extend background clip
- idempotent timeline layer
- bridge gap with same clip
- ensure overlay coverage
- append media at record frame

## What it does

Fill a video layer across the selected range.

## Do not use when

Do not use this command for audio/subtitle layers, ripple editing, replacing an occupied range, moving a clip earlier, trimming source in/out, or composing several clips across the range. It guarantees at most one matching timeline item spanning the entire target.
Do not automatically retry an insertion or extension error.

## Preflight and readback

Before execution, save/checkpoint the project; inspect the exact target timeline, record-frame coordinates, video track inventory, every item crossing the range, matching media identity, source length, and available gap.
Confirm the intended timeline remains open, added tracks are acceptable, exactly the intended media spans the range, neighboring clips and links are unchanged, source content is valid for the full duration, and playback/render output is correct.

## Public arguments and options

- `--media` (required) — Media Pool item name, id, or source path
- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--track` (required) — Target video track index
- `--start-frame` (required) — DaVinci Resolve recordFrame where the layer must start
- `--duration` (required) — Required target duration in frames
- `--extend-gap` (optional, default: `"0f"`) — Maximum gap to bridge, e.g. 1s, 25f, or a bare frame count
- `--match-name` (optional, default: `"exact"`) — Media name matching mode: exact or contains
- `--allow-insert/--no-insert` (optional, default: `true`) — Insert the media when no suitable existing item is found
- `--allow-extend/--no-extend` (optional, default: `true`) — Extend a nearby matching item when possible
- `--dry-run` (optional, default: `false`) — Plan the operation without mutating DaVinci Resolve

## Boundaries and gotchas

- The command is mutating unless effective dry-run is enabled.
- Both the command-local `--dry-run` and global dry-run are honored.
- Track is required, video-only, 1-based, and must be at least 1.
- Start frame is a required nonnegative integer DaVinci Resolve `recordFrame`, not a timecode/seconds expression.
- Duration is a required positive integer frame count.
- `--extend-gap` defaults to `0f`.
- `--match-name` accepts only `exact` or `contains`.
- `--timeline NAME` switches that project timeline current.
- Readable nonmatching items outside the target range are ignored.
- A matching item is extendable when its range overlaps the target or its gap is no greater than `--extend-gap`.
- Extension can only preserve the current item start and lengthen its tail.
- A match beginning after the requested target start enters the extendable branch but then fails because the command cannot move it earlier.
- That earlier-start failure does not fall through to insertion.
- The command does not preflight that the source has enough frames for the requested insertion duration.
- Save failure is recorded in append details but does not itself abort.
- Extension coverage is numeric and does not verify media content, source frames, visual output, links, transitions, or neighboring item integrity.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `TIMELINE_CONFLICT`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline layer ensure-media --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
