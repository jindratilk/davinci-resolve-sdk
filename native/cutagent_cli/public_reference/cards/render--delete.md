# `render delete`

Syntax: `cutagent render delete [--job VALUE] [--all]`

## Search terms

- delete render job
- remove queued render
- delete all render jobs
- render job queue index
- exact JobId selector
- clear Deliver queue

## What it does

Delete render jobs.

## Do not use when

Do not delete jobs that contain render settings or history you still need. This command has no undo or queue reconstruction.
Do not assume a numeric selector is always an index. An exact numeric JobId takes precedence.
Do not treat a successful response as readback verification that jobs disappeared; this command does not re-list the queue after deletion.

## Preflight and readback

Before execution, run `render jobs`, preserve the complete queue, identify the exact JobId and its 1-based position, and confirm that no active or externally managed workflow still depends on the job.
Confirm any active render behavior separately. Recreate a mistakenly deleted job manually from saved settings.

## Public arguments and options

- `--job` (optional) — Job ID to delete
- `--all` (optional, default: `false`) — Delete all jobs

## Boundaries and gotchas

- Exact help is `cutagent render delete (--job TEXT | --all)`.
- Exactly one of `--job` and `--all` is required.
- A successful `--job 2` dry-run does not prove queue item 2 exists.
- The command does not stop an active render before deletion.
- Use `render cancel --delete-queued` when stop-plus-delete semantics and post-delete id checking are required.
- Deletion is manually recoverable only by recreating jobs.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
