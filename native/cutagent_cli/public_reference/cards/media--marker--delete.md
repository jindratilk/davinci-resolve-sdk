# `media marker delete`

Syntax: `cutagent media marker delete NAME [--frame VALUE] [--color VALUE]`

## Search terms

- delete Media Pool marker
- remove source marker by frame
- clear source markers by color
- erase marker from imported asset
- delete all red media markers
- remove reusable clip annotation
- clean Media Pool review cues
- unmark source frame

## What it does

Delete marker(s) from a clip.

## Do not use when

Use `clip marker delete` for a marker owned by one timeline item and `timeline marker delete` for a fixed timeline marker. Do not use color mode when only one of several same-color source notes should go—list and delete its exact source frame.

## Preflight and readback

Run media marker list in the asset's folder and capture exact affected markers; if the source appears in edits, scan occurrences too. Choose one selector only. Recreate from captured metadata if deletion was accidental.

## Public arguments and options

- `NAME` (required) — Clip name
- `--frame` (optional) — Frame number
- `--color` (optional) — Marker color

## Boundaries and gotchas

- At least one selector is required.
- If both are supplied, `--frame` wins and `--color` is ignored rather than intersected.
- Project-wide name matching is used for deletion, while the verification list command searches only the current folder.
- Dry-run echoes the selector without checking clip existence or matching markers.

## Examples

- `cutagent media marker delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
