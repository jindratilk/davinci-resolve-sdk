# `media marker list`

Syntax: `cutagent media marker list NAME`

## Search terms

- list Media Pool markers
- show source asset annotations
- inspect markers on imported clip
- get source marker frames
- verify Media Pool marker
- find media marker name and note
- check source markers before edit

## What it does

List markers on a clip.

## Do not use when

Use `timeline clip-markers list` to find where Media Pool markers occur in the active edit and obtain record frames. Use `clip marker list` for marker state attached to a specific timeline item, and `timeline marker list` for fixed timeline annotations. Do not rely on a bare name when duplicates exist in different Media Pool folders; use search/folder context to disambiguate the intended asset first.

## Preflight and readback

Confirm the asset's folder identity, then list before mutations to preserve exact source frames and metadata. For an edited source, follow with a timeline-wide occurrence scan.

## Public arguments and options

- `NAME` (required) — Clip name

## Examples

- `cutagent media marker list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
