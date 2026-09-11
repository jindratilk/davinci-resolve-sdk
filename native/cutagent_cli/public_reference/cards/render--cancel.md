# `render cancel`

Syntax: `cutagent render cancel [--job VALUE] [--delete-queued]`

## Search terms

- cancel active render
- stop DaVinci Resolve rendering
- delete queued render job
- cancel render queue
- render job selector
- delete all render jobs
- stop current Deliver job
- cancel preview dry run

## What it does

Cancel active rendering.

## Do not use when

Do not use when another render must continue. Stopping is global to the current project render operation, not scoped to the `--job` selector.
Do not add `--delete-queued` unless permanent queue removal is intended and the jobs have been recorded or can be reconstructed.
Do not assume `--job` cancels only that job. It selects a queue item only for validation, reporting, and optional deletion.

## Preflight and readback

Before execution, run `render jobs`, identify the current active render independently, save the full queue configuration, and resolve a selector to its exact JobId. Confirm whether only stopping or stopping plus deletion is intended.
After execution, confirm rendering is no longer active. Recreate deleted jobs manually if they were removed unintentionally.

## Public arguments and options

- `--job` (optional) — Optional job ID to target
- `--delete-queued` (optional, default: `false`) — Delete queued job(s) as well

## Boundaries and gotchas

- Exact help is `cutagent render cancel [--job TEXT] [--delete-queued]`.
- Without `--delete-queued`, the selector changes only validation/reporting; no queue entry is deleted.
- Without `--job`, `--delete-queued` means delete every queue job.
- Queue deletion cannot be rolled back by this command.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent render cancel --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
