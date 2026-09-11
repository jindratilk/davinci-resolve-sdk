# `fusion image set`

Syntax: `cutagent fusion image set --image VALUE [--clip VALUE] [--track VALUE] [--record-frame VALUE] [--group-tool VALUE] [--group-input VALUE] [--import-media] [--zoom-x VALUE] [--zoom-y VALUE] [--pan VALUE] [--tilt VALUE] [--position-x VALUE] [--position-y VALUE]`

## Search terms

- set Fusion image source
- replace MediaIn source
- set Loader filename
- inject image into template
- Fusion group image input
- MediaID image assignment
- image source visual verification
- restore Fusion source media
- Fusion image dry-run

## What it does

Update a Fusion image source.

## Do not use when

The command supplies no checkpoint, undo token, or automatic restoration.
Do not leave `--import-media` enabled when Media Pool insertion is unwanted. Newly imported items remain after command completion and must be cleaned only after graph restoration.
Do not use `--group-tool` without `--group-input`, and do not guess group/input names. Inspect the graph first.
Do not trust dry-run selector validity.

## Preflight and readback

Before execution, inspect the target timeline and composition, record the exact clip or paired track/record frame, enumerate Loader/MediaIn/group tools, and capture original source paths or Media IDs.
Export a representative before-frame and retain the original media path needed for restoration.
Separately validate selector pairing because dry-run does not.
Then export and visually inspect a frame or render.
Remove any uniquely imported Media Pool item only after restoration.

## Public arguments and options

- `--image/--image-path` (required) — Local image file to inject
- `--clip` (optional) — Clip name selector
- `--track` (optional) — Video track index selector
- `--record-frame` (optional) — Record-domain point selector
- `--group-tool` (optional) — Preferred group tool name
- `--group-input` (optional) — Preferred group input name
- `--import-media/--no-import-media` (optional, default: `true`) — Import image into Media Pool before MediaID assignment
- `--zoom-x` (optional) — Transform ZoomX value
- `--zoom-y` (optional) — Transform ZoomY value
- `--pan` (optional) — Transform Pan value
- `--tilt` (optional) — Transform Tilt value
- `--position-x` (optional) — Alias for Pan
- `--position-y` (optional) — Alias for Tilt

## Boundaries and gotchas

- `--image TEXT` / `--image-path TEXT` is required.
- Target options are `--clip`, `--track`, and `--record-frame`.
- Group options are `--group-tool` and `--group-input`.
- Media import is controlled by `--import-media/--no-import-media` and defaults to import.
- Transform options are `--zoom-x`, `--zoom-y`, `--pan`, `--tilt`, `--position-x`, and `--position-y`.
- `--clip` cannot be combined with track/record-frame targeting.
- Dry-run does not connect, inspect the graph, import media, or prove visual compatibility.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion image set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
