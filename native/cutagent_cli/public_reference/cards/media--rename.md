# `media rename`

Syntax: `cutagent media rename OLD NEW`

## Search terms

- rename Media Pool clip
- change source item display name
- rename imported footage in project
- give asset a clearer clip name
- change bin item name
- rename timeline-linked source
- restore original Media Pool name
- label source clip without renaming file

## What it does

Rename a media pool item.

## Do not use when

Use a timeline-item rename command when only one occurrence should get a local name while the shared source remains unchanged. Use `media move` when the organizational change is bin location rather than name.

## Preflight and readback

Exact-search the old name and record folder, source path, Media Pool ID, and all linked timeline occurrences. Inspect timeline items to prove whether their displayed name followed the source and confirm ID/path/timing stayed fixed.

## Public arguments and options

- `OLD` (required) — Current Media Pool clip name
- `NEW` (required) — New Media Pool clip name

## Examples

- `cutagent media rename --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
