# `clip marker custom-data`

Syntax: `cutagent clip marker custom-data CLIP_OR_FRAME FRAME_OR_DATA [MAYBE_DATA] [--clip VALUE]`

## Search terms

- set marker custom data
- tag clip marker with stable token
- add machine identifier to marker
- attach hidden data to clip marker
- make marker retrievable by token
- label source marker for automation

## What it does

Set custom data on a clip marker.

## Do not use when

Do not use it to change the marker's visible name or note; this only changes hidden custom data.

## Preflight and readback

Choose a namespaced unique string and record any existing token that will be replaced.

## Public arguments and options

- `CLIP_OR_FRAME` (required) — Clip name or marker frame
- `FRAME_OR_DATA` (required) — Marker frame or custom data
- `MAYBE_DATA` (optional) — Custom marker data when clip is positional
- `--clip` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- With three arguments, the first is always treated as clip name; with two, the first must parse as an integer frame and clip comes from `--clip` or current item.
- The command does not enforce uniqueness across markers or inspect an existing value before overwrite.

## Examples

- `cutagent clip marker custom-data --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
