# `color group clips`

Syntax: `cutagent color group clips GROUP`

## Search terms

- list clips in Color group
- show grading group members
- verify clip group assignment
- find shots sharing group grade
- enumerate timeline items in color group
- inspect group membership
- get grouped clip unique IDs

## What it does

List timeline clips assigned to a color group.

## Do not use when

Do not use response index as a stable clip selector; use the returned unique ID for identity evidence and an explicit name/track-frame selector for later commands.

## Preflight and readback

Run after every assign/remove/rename/delete that changes expected membership. Compare unique IDs rather than names when duplicate clip names exist.

## Public arguments and options

- `GROUP` (required) — Color group name

## Boundaries and gotchas

- The response itself does not include timeline name.
- The command does not report whether group pre/post nodes are enabled, what they do, or whether the grouped clips render differently.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent color group clips --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
