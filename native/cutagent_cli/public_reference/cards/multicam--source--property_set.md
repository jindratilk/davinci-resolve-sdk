# `multicam source property-set`

Syntax: `cutagent multicam source property-set KEY VALUE --angle VALUE --record-frame VALUE [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--media-type VALUE]`

## Search terms

- multicam source property
- exact nested media pool item
- source clip metadata
- match frame property set

## What it does

Change a multicam source property.

## Do not use when

Do not use in an intentional gap. Do not use generic clip-name matching when repeated source items require exact angle/frame identity.

## Preflight and readback

Run match-frame and capture the original value.

## Public arguments and options

- `KEY` (required) — Media Pool clip property key, including camera RAW properties exposed by DaVinci Resolve
- `VALUE` (required) — Requested property value
- `--angle` (required)
- `--record-frame` (required) — Frame relative to the multicam start inside the desired source item
- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--media-type` (optional, default: `"video"`) — video or audio

## Boundaries and gotchas

- `--angle` is one-based and `--record-frame` is relative.
- `--key` and `--value` are required.

## Examples

- `cutagent multicam source property-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
