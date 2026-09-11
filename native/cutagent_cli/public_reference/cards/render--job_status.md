# `render job-status`

Syntax: `cutagent render job-status JOB_ID`

## Search terms

- render job status
- inspect one render job
- render queue progress
- CompletionPercentage
- 1-based render queue index
- IsRenderingInProgress

## What it does

Check status for a single render job.

## Do not use when

That flag is project-global.
Do not rely on a numeric selector as a stable queue identity. Exact numeric JobIds take precedence, and index positions can change.

## Preflight and readback

Before querying, prefer an exact JobId captured from `render jobs` or a queueing command.
Correlate it with global rendering state and verify any completed artifact on disk.

## Public arguments and options

- `JOB_ID` (required) — Render job ID

## Boundaries and gotchas

- The command is read-only and requires a current project.
- No command-specific dry-run branch exists.
- Zero, negative, out-of-range, missing, or id-less indexed entries fail selection.
- An empty queue with a required selector is an error, not an empty successful status.
- Available-job error summaries normalize only selected fields.
- The command does not wait, poll, mutate, or verify an output file.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`
- `VALIDATION_ERROR`

## Examples

- `cutagent render job-status --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
