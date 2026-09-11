# `media property-set`

Syntax: `cutagent media property-set NAME KEY VALUE`

## Search terms

- set Media Pool clip property
- change source start timecode
- set input color space property
- change reel or timecode property

## What it does

Set a clip property.

## Do not use when

Use `media metadata CLIP KEY VALUE` for metadata fields such as Comments and Keywords. Use `media rename` for a clearer, purpose-specific item rename and `media color set`/flag commands for their validated palettes. Do not use arbitrary property keys without first reading `media info` and confirming DaVinci Resolve documents the property as writable; many returned properties are read-only.

## Preflight and readback

Dry-run the final key/value. Restore the recorded value when testing.

## Public arguments and options

- `NAME` (required) — Clip name
- `KEY` (required) — Property key
- `VALUE` (required) — Property value

## Boundaries and gotchas

- The response exposes only the post-readback value, not the prior value, setter return, or an undo/checkpoint.

## Examples

- `cutagent media property-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
