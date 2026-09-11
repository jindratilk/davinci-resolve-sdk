# `timeline output-blanking get`

Syntax: `cutagent timeline output-blanking get [--item-id VALUE]`

## Search terms

- output blanking
- image bounds
- letterbox
- clip blanking inheritance

## What it does

Read output blanking and clip inheritance without modifying the timeline.

## Do not use when

Do not use this as a crop or scale operation. Titles and generators may not provide clip-level blanking.

## Preflight and readback

An inherited clip returns no active clip override and reports effective timeline bounds. Verify the returned state and preserve unrelated clips.

## Public arguments and options

- `--item-id` (optional) — Exact video timeline item ID; omit for timeline blanking

## Boundaries and gotchas

- --use-timeline and --use-clip require an exact --item-id and cannot be combined with edge values.

## Examples

- `cutagent timeline output-blanking get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
