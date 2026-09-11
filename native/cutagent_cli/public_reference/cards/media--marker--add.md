# `media marker add`

Syntax: `cutagent media marker add NAME FRAME [--color VALUE] [--name VALUE] [--note VALUE] [--duration VALUE]`

## Search terms

- add marker to Media Pool clip
- mark source asset
- create source marker on media
- annotate every timeline occurrence
- add reusable clip cue
- put note on imported media
- flag source frame before editing
- add Media Pool review marker

## What it does

Add a marker to a clip.

## Do not use when

Use `clip marker add` when the annotation must belong only to one timeline item/occurrence. Use `timeline marker add` when it must stay at a record position if clips move.

## Preflight and readback

Search/list the Media Pool and identify the exact asset/folder, inspect existing source markers, then choose an unoccupied source frame and supported color. If the asset is already edited, use `timeline clip-markers list` to verify how the source marker maps into each occurrence.

## Public arguments and options

- `NAME` (required) — Clip name
- `FRAME` (required) — Frame number
- `--color` (optional, default: `"Blue"`) — Marker color
- `--name` (optional, default: `""`) — Marker name
- `--note` (optional, default: `""`) — Marker note
- `--duration` (optional, default: `1`) — Marker duration in frames

## Boundaries and gotchas

- Duplicate clip names in different folders can make a bare name an unsafe identity even though one match is chosen.

## Examples

- `cutagent media marker add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
