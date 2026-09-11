# `timeline marker batch`

Syntax: `cutagent timeline marker batch [--batch VALUE] [--batch-json VALUE] [--spec-json VALUE] [--timeline-name VALUE] [--default-color VALUE] [--prefix VALUE] [--shift-occupied]`

## Search terms

- batch add timeline markers
- import review notes from JSON
- add markers for transcript ranges
- create many edit annotations
- mark multiple highlight ranges
- add collision-safe timeline cues
- target markers to named timeline
- turn detected sections into markers
- add chapter markers from JSON
- bulk timeline flags

## What it does

Update timeline markers.

## Do not use when

Use `timeline marker add` for one precisely controlled marker on the active timeline; it has clearer mixed absolute/relative position semantics. Do not use this for video/audio in/out ranges (`timeline mark set`) or clip/source markers. Do not use `--shift-occupied` when exact frame identity is contractually important; choose `--no-shift-occupied` and handle the preflight error instead. Do not target a named timeline when changing the user's active timeline is unacceptable without planning to restore it.

## Preflight and readback

List timelines and the target timeline's existing markers, then prepare exactly one JSON input form. Rerun `timeline marker list` on the now-active target and switch back to the previously active timeline if `--timeline-name` was used.

## Public arguments and options

- `--batch` (optional) — Batch JSON path
- `--batch-json` (optional)
- `--spec-json` (optional)
- `--timeline-name/--timeline` (optional) — Target timeline name; defaults to active timeline
- `--default-color` (optional, default: `"Blue"`)
- `--prefix` (optional, default: `""`) — Prefix prepended to each marker name
- `--shift-occupied/--no-shift-occupied` (optional, default: `true`) — Auto-shift marker collisions by +1 frame

## Boundaries and gotchas

- Exactly one of `--batch`, `--batch-json`, or `--spec-json` is required.
- The JSON must be an array of objects or an object containing a `markers` or `ranges` array.
- Unlike single `marker add`, it does not apply the command's absolute-timecode heuristic; use explicit record range fields when the source data is in record domain.
- Range duration is `end - start`, with a minimum of one frame.
- With `--no-shift-occupied`, any occupied frame makes the whole preflight fail before creating entries.
- Dry-run planning resolves the named timeline without activating it.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent timeline marker batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
