# `project delete`

Syntax: `cutagent project delete NAME [--force]`

## Search terms

- delete DaVinci Resolve project
- permanently remove project
- close current project before delete
- verify project deletion
- project deletion force
- current folder project removal
- irreversible project mutation
- deletion readback polling

## What it does

Delete a project.

## Do not use when

Matching is exact but scoped to the current folder.

## Preflight and readback

Supply `--force` only after this evidence.
If closing succeeds but deletion fails, recognize that the project may remain closed; reopen it manually before continuing work.

## Public arguments and options

- `NAME` (required) — Project name
- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- Exact syntax is `cutagent project delete NAME [--force]`.
- `--force` has no effect during global dry-run.
- Name matching is exact/case-sensitive and limited to the current folder.

## Stable public error codes

- `CONFIRMATION_REQUIRED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent project delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
