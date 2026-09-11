# `render start`

Syntax: `cutagent render start [--jobs VALUE] [--wait]`

## Search terms

- start render queue
- render selected job IDs
- wait for render completion
- start all queued renders
- auto-add full timeline job
- nonblocking render start
- comma-separated render jobs
- Deliver queue execution

## What it does

Start rendering.

## Do not use when

Do not run this while another render is active.
Do not omit `--jobs` when only a specific subset may render.
Do not use the default unbounded wait in orchestration that requires a hard deadline; use a separate monitored workflow with `render wait --timeout`.

## Preflight and readback

Use `--no-wait` only if another process will monitor `render status` or `render wait`. Use exact comma-separated IDs with no ambiguous aliases.
After a blocking start, inspect every selected job status and output file even though the command reports completion. After a nonblocking start, monitor until terminal state and validate the rendered media. Remove any automatically added job if it is no longer wanted.

## Public arguments and options

- `--jobs` (optional) — Comma-separated job IDs
- `--wait/--no-wait` (optional, default: `true`) — Wait for completion

## Boundaries and gotchas

- Exact help is `cutagent render start [--jobs IDS] [--wait/--no-wait]`.
- Dry-run does not inspect the queue, settings, active-render state, output path, or job IDs.
- The empty-queue path does not itself validate output target/name before adding.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render start --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
