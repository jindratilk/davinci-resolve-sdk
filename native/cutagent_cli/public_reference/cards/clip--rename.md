# `clip rename`

Syntax: `cutagent clip rename OLD_NAME NEW_NAME`

## Search terms

- rename timeline clip
- change clip display name
- label an edit occurrence
- give timeline item a custom name
- rename selected video clip
- organize edit with descriptive clip names
- restore timeline clip name
- distinguish repeated takes by name

## What it does

Rename a timeline clip.

## Do not use when

Use `clip color`, flags, or markers when the request is categorization rather than a name change.

## Preflight and readback

List the track and record the item's start/end, source filename, display name, and any same-name duplicates. Rename, then query both the new display name and the original source name; confirm the returned object's timing/track is the intended occurrence. Never rely on global `--dry-run` for this command.

## Public arguments and options

- `OLD_NAME` (required) — Current clip name
- `NEW_NAME` (required) — New name

## Boundaries and gotchas

- `--dry-run` is broken and mutating.
- This does not create a unique selector.

## Examples

- `cutagent clip rename --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
