# `clip info`

Syntax: `cutagent clip info [NAME]`

## Search terms

- inspect timeline clip details
- get clip start end duration
- show item offsets and properties
- look up clip occurrence by name
- inspect current clip under playhead
- check Fusion comp count on clip
- get timeline item metadata

## What it does

Check detailed clip info.

## Do not use when

Use `clip list` to enumerate occurrences before choosing one, `clip source-range` for explicit source-domain fields, `clip properties --get KEY` for one property, and `media info` for Media Pool/source metadata. Use selector-aware mutation/readback commands with `--at` when duplicate timeline names exist. Do not use this as proof of link state or track identity; those require `clip linked list` and `clip track-info`.

## Preflight and readback

List relevant tracks and establish whether the name is unique. If omitting the name, set the playhead and account for stacked-item priority. After reading, corroborate start/end with `clip list`, source frames with `clip source-range`, and track with `clip track-info` before targeting an edit.

## Public arguments and options

- `NAME` (optional) — Clip name (or current if omitted)

## Boundaries and gotchas

- It does not detect or report ambiguity.
- Matching considers display name, clip/file/path properties, Media Pool name and path, with exact and case-insensitive basename comparisons.
- Use `clip source-range` when source-domain semantics matter.

## Examples

- `cutagent clip info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
