# `render status`

Syntax: `cutagent render status [--job VALUE]`

## Search terms

- render status
- current render queue state
- specific render job status
- render job by index
- CompletionPercentage readback
- monitor active render
- raw render job dictionary

## What it does

Check render status.

## Do not use when

Do not use the global `rendering` field alone to infer the outcome of a particular job.
Do not expect normalized job fields; use `render jobs` for a compact normalized listing.

## Preflight and readback

Before execution, ensure the intended project is current and use `render jobs` to capture exact IDs. Prefer exact IDs over queue indices because queue ordering can change.
Poll at a controlled interval and preserve the full raw job dictionary when diagnosing DaVinci Resolve-specific status fields.
After a terminal status, inspect the expected output file and media.

## Public arguments and options

- `--job` (optional) — Specific job ID

## Boundaries and gotchas

- Exact help is `cutagent render status [--job JOB]`.
- A selected scalar entry can resolve an ID but produce an empty `jobs` array because final output keeps dictionaries only.
- The command does not wait, apply a timeout, infer terminal success, or inspect output files.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render status --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
