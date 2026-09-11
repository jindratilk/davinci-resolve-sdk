# `render stop`

Syntax: `cutagent render stop`

## Search terms

- stop active render
- cancel global rendering
- interrupt Deliver render
- halt render queue execution
- stop all active render work
- emergency render stop
- preserve queued jobs after stop

## What it does

Stop rendering.

## Do not use when

Do not use this when you only want to remove a queued job without stopping active rendering; use `render delete`.
Do not expect it to target one active job selectively.
Do not use it without understanding that an in-progress output may be incomplete and require manual cleanup.

## Preflight and readback

Before execution, capture `render status` and `render jobs`, identify affected outputs, and decide whether queued jobs should remain.
Use `render cancel --delete-queued` when stopping plus queue deletion is the intended combined workflow.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- It does not first check whether a render is active.
- It does not resolve or accept a job ID.
- The command does not delete one or all queue jobs.
- It does not remove partial output media.
- It does not capture the active job or output path before stopping.
- Stopping cannot roll back already written frames or files.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent render stop --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
