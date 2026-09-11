# `timeline track items`

Syntax: `cutagent timeline track items TRACK_TYPE INDEX`

## Search terms

- list items on timeline track
- inspect video track clips
- inspect audio track clips
- inspect subtitle track items
- timeline item source identity
- timeline item frame bounds
- Media Pool item IDs

## What it does

List clips on a specific track.

## Do not use when

Do not use this to list track-level names, enabled/locked state, or all tracks; use `timeline track list`.
Do not assume names alone identify clips. Use timeline-item and Media Pool identifiers plus source path and frame bounds where available.

## Public arguments and options

- `TRACK_TYPE` (required) — video, audio, subtitle
- `INDEX` (required) — Track index

## Boundaries and gotchas

- Index must be an integer at least 1.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline track items --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
