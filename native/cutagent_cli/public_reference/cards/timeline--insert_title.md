# `timeline insert-title`

Syntax: `cutagent timeline insert-title NAME [--fusion]`

## Search terms

- timeline insert-title
- Insert a title into the timeline at the playhead.
- timeline insert-title help
- timeline insert-title command

## What it does

Insert a title into the timeline at the playhead.

## Do not use when

Do not use this command when exact track, duration, position, styling, or Fusion inputs must be supplied. Use a text/template workflow that explicitly owns those properties.
Do not automatically retry after a readback failure.

## Preflight and readback

Before execution, checkpoint the project; inspect the active timeline, playhead, target/enabled/locked video tracks, surrounding items, and the exact standard/Fusion title asset name available in DaVinci Resolve.
Use dry-run to confirm asset name and standard/Fusion route only. It does not connect, validate the asset catalog, inspect placement, or predict duration.
After execution, inspect the returned method/asset/clip/track/bounds fields, re-enumerate the timeline, and confirm exactly one new title at the intended placement.

## Public arguments and options

- `NAME` (required) — Title name
- `--fusion` (optional, default: `false`) — Insert a Fusion title

## Boundaries and gotchas

- An active timeline is required.
- The command does not enumerate the Effects Library/title catalog before insertion.
- The command does not set visible title text, font, style, layout, duration, or track.
- At least one comparable field must match.
- It does not verify title text/style, Fusion graph, rendered pixels, overlaps, or track compositing.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`

## Examples

- `cutagent timeline insert-title --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
