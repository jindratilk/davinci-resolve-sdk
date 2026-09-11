# `color group add`

Syntax: `cutagent color group add GROUP_NAME`

## Search terms

- create Color group
- add shared grading group
- make pre-clip post-clip group
- group clips for common grade
- create project color group
- set up shared Color-page corrections
- add DaVinci Resolve color group

## What it does

Add a color group.

## Do not use when

Use `color group assign` when the group already exists and the task is to place a clip in it, `color group rename` to change an existing group's name, and `color group graph` to inspect pre/post node counts. Do not confuse Color groups with Gallery albums, clip colors/flags, linked clips, media-pool bins, or Fusion compositions; those are separate organizational/grade systems.

## Preflight and readback

List groups first and choose a unique, stable name. After add, list again and require one exact row with that name before assigning clips or editing the pre/post graphs. If this is a workflow setup, then assign explicit clips one at a time and confirm membership with `color group clips`.

## Public arguments and options

- `GROUP_NAME` (required) — Color group name

## Boundaries and gotchas

- DaVinci Resolve rejects duplicate group names.
- The command does not trim or validate the name in Python and has no command-specific dry-run preview.
- Avoid blank/whitespace names and do not use dry-run as the sole safety check.
- It does not require or change the current timeline.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent color group add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
