# `timeline delete`

Syntax: `cutagent timeline delete NAME [--force]`

## Search terms

- delete timeline
- remove sequence from project
- permanently delete an edit
- delete named timeline
- remove scratch timeline
- clean up test sequence
- delete current timeline
- discard timeline version

## What it does

Delete a timeline.

## Do not use when

Do not use this to delete clips while retaining the timeline; use `timeline items delete`. Do not target by assumed current state when exact name has not been listed.

## Preflight and readback

List timelines, inspect the target, save/export/checkpoint if recovery matters, and dry-run the exact name. In machine mode add `--force` only after those checks.

## Public arguments and options

- `NAME` (required) — Timeline name
- `--force/-f` (optional, default: `false`)

## Boundaries and gotchas

- Duplicate-looking names or other project folders are not considered.
- Source media in the Media Pool is not removed, but timeline-only compositions/markers/edit decisions disappear with the timeline.

## Stable public error codes

- `CONFIRMATION_REQUIRED`

## Examples

- `cutagent timeline delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
