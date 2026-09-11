# `clip source-range`

Syntax: `cutagent clip source-range [CLIP]`

## Search terms

- get source in and out for timeline clip
- inspect source frames used by occurrence
- compare timeline range to media range
- find clip handles left right
- source-domain readback for edit item
- verify append source slice
- check trimmed source range
- map timeline item to source frames

## What it does

Check source range information for a timeline item.

## Do not use when

Use `clip info` for broader item properties/Fusion count, `clip list` for all record ranges on a track, and Media Pool info for full source duration/path. Use `timeline item move`/append commands to change ranges.

## Preflight and readback

Confirm the exact occurrence with track list/name uniqueness. Record timeline fps and source fps when comparing frame counts. After trims/appends/retimes, rerun this command and compare both source and record fields, then inspect visible first/last frames because raw endpoint conventions can differ.

## Public arguments and options

- `CLIP` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- Missing source-range methods are silently skipped; success can contain only offsets/timeline fields.
- Retime/freeze/reverse items may expose source ranges that do not fully describe time mapping.

## Examples

- `cutagent clip source-range --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
