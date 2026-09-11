# `clip marker add`

Syntax: `cutagent clip marker add FRAME [--color VALUE] [--name VALUE] [--note VALUE] [--duration VALUE] [--frame-domain VALUE] [--clip VALUE]`

## Search terms

- add marker to clip
- attach note that follows clip
- mark source frame
- add clip-offset annotation
- flag moment inside timeline item
- create clip marker on audio item
- add review note to clip
- mark trimmed source position

## What it does

Add a marker to a clip.

## Do not use when

Do not use it for a fixed timeline-position marker (`timeline marker add`) or an in/out range (`timeline mark set`). Use a Media Pool marker command when the annotation must exist on the source asset before or independent of timeline placement. Avoid `auto` when a trimmed clip has nonzero source start and the number could plausibly be either an offset or source frame; specify the domain.

## Preflight and readback

Translate the user's position into an explicit source or offset domain and ensure the frame is unoccupied.

## Public arguments and options

- `FRAME` (required) — Marker frame value
- `--color` (optional, default: `"Blue"`)
- `--name` (optional, default: `""`)
- `--note` (optional, default: `""`)
- `--duration` (optional, default: `1`)
- `--frame-domain` (optional, default: `"auto"`) — Frame domain: auto, offset, source, or raw
- `--clip` (optional)

## Boundaries and gotchas

- There is no command-local dry-run branch.

## Examples

- `cutagent clip marker add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
