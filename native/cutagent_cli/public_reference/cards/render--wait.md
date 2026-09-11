# `render wait`

Syntax: `cutagent render wait [--jobs VALUE] [--timeout-s VALUE] [--poll-ms VALUE]`

## Search terms

- wait for render completion
- poll render queue
- render timeout
- selected render job wait
- IsRenderingInProgress polling
- CompletionPercentage monitor
- blocking render verification
- comma-separated job IDs
- canonical render wait

## What it does

Wait for rendering to finish.

## Do not use when

Do not run without `--timeout-s` in automation that must have a bounded completion time.
Do not pass queue indices; this command validates exact job IDs only.
Do not treat returned completion as proof that an output file exists or contains valid media.

## Preflight and readback

Before execution, run `render jobs`, capture exact IDs, choose a timeout longer than the expected render but shorter than the orchestration deadline, and use a reasonable poll interval.
Ensure another unrelated render cannot keep the global active flag true unexpectedly when waiting for a subset.

## Public arguments and options

- `--jobs` (optional) — Comma-separated job IDs
- `--timeout-s` (optional) — Optional timeout
- `--poll-ms` (optional, default: `500`) — Polling interval in milliseconds

## Boundaries and gotchas

- Exact help is `cutagent render wait [--jobs IDS] [--timeout-s SECONDS] [--poll-ms MILLISECONDS]`.
- Timeout must be strictly positive when supplied.
- Poll interval must be strictly positive.
- Only dictionary queue entries participate in status/progress polling.
- A timeout error includes only timeout, last progress, and last status.
- Failure/cancellation is raised only once global activity and recognized matching active statuses have stopped.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render wait --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
