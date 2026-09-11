# `timeline marker delete`

Syntax: `cutagent timeline marker delete [--frame VALUE] [--color VALUE] [--all]`

## Search terms

- delete timeline marker
- remove marker at frame
- clear markers by color
- delete all timeline notes
- remove red review flags
- erase point marker
- clean timeline annotations
- delete marker at record frame

## What it does

Delete markers.

## Do not use when

Do not use it for clip/source markers. Do not choose color mode when only one of several same-color notes should be removed; list markers and delete the exact frame. Do not use `--all` in a timeline whose review annotations have not been captured, because this command does not provide undo data or recreate marker metadata.

## Preflight and readback

Run `timeline marker list` and verify the active timeline, frame domain, and affected count. For broad cleanup, checkpoint or export marker details first.

## Public arguments and options

- `--frame` (optional, repeatable) — Delete marker at an exact frame; repeat for multiple markers
- `--color` (optional) — Delete all markers of a color
- `--all` (optional, default: `false`) — Delete all markers

## Boundaries and gotchas

- If several selectors are supplied, precedence is `--all`, then `--color`, then `--frame`; do not combine them expecting an intersection.
- There is no interactive choice and no command-local dry-run branch.

## Examples

- `cutagent timeline marker delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
