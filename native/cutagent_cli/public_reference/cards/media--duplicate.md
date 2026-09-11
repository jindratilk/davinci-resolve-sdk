# `media duplicate`

Syntax: `cutagent media duplicate NAME [--new-name VALUE]`

## Search terms

- duplicate Media Pool clip
- create second project reference to source
- copy asset into another bin
- clone imported media item
- make alternate Media Pool clip
- duplicate footage with new name
- reimport source as separate clip
- create another bin instance of audio

## What it does

Duplicate a media pool clip.

## Do not use when

Use `media move` when the same Media Pool object should merely change bins. Use `media import` for a different source file or when duplication semantics are unnecessary. Use timeline clip duplication/copy commands when the desired duplicate is an additional timeline occurrence.

## Preflight and readback

Exact-search the source and record its folder, source path, annotations, marks, and metadata. Supply a unique `--new-name`, then exact-search both source and duplicate, prove they share source path but are separate Media Pool items, and compare every per-item property the workflow needs. Delete only the duplicate after testing, not the source used by timelines.

## Public arguments and options

- `NAME` (required) — Clip name
- `--new-name` (optional) — Optional new clip name

## Boundaries and gotchas

- The response does not include folder, new object ID, source path, or copied-property comparison.
- Without `--new-name`, DaVinci Resolve chooses the resulting name.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent media duplicate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
