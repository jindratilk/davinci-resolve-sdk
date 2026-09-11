# `timeline rename`

Syntax: `cutagent timeline rename NEW_NAME [--source VALUE]`

## Search terms

- rename timeline
- change sequence name
- rename current edit
- rename another timeline by source name
- give timeline a new name
- fix timeline naming
- label sequence version
- rename non-current timeline

## What it does

Rename a timeline.

## Do not use when

Do not use it to rename the project (`project rename`) or a track (`timeline track rename`). Do not omit `--source` when the current timeline is not the intended target. Do not try to resolve a collision by overwriting: the command refuses an existing timeline name.

## Preflight and readback

List timelines and capture exact source/current names. Dry-run the intended source and target, then execute.

## Public arguments and options

- `NEW_NAME` (required) — New timeline name
- `--source` (optional) — Optional source timeline name; defaults to current timeline

## Boundaries and gotchas

- Names are trimmed, so leading/trailing spaces cannot intentionally distinguish timelines.
- Without `--source`, an active timeline is required.
- With a source, only an open project is required and the named timeline need not be current.
- The command changes identity only; downstream scripts, external notes, or filenames containing the old timeline name are not updated.

## Examples

- `cutagent timeline rename --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
