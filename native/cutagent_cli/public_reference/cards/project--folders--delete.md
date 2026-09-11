# `project folders delete`

Syntax: `cutagent project folders delete NAME [--force]`

## Search terms

- remove Project Manager folder
- folder management force
- irreversible project folder cleanup
- delete empty project folder
- project library folder removal

## What it does

Delete a project folder in the current folder.

## Do not use when

Do not delete a folder until its projects/subfolders are listed and preserved or intentionally disposable. The command does not preflight contents.
Do not rely on this command for post-delete verification.

## Preflight and readback

Export/archive/back up any project that may be needed.
Supply `--force` only after verifying removal is safe.
Confirm no sibling folder/project changed and that the current Project Manager path remains valid.

## Public arguments and options

- `NAME` (required) — Folder name
- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- Exact syntax is `cutagent project folders delete NAME [--force]`.
- Consequently, whitespace names can pass dry-run.
- `--force` has no effect during global dry-run.
- Null also returns `deleted:false` without raising because only `is False` is rejected.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `CONFIRMATION_REQUIRED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent project folders delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
