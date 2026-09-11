# `render jobs`

Syntax: `cutagent render jobs`

## Search terms

- list render queue
- queued render jobs
- render progress list
- CompletionPercentage
- output filename render job
- Deliver queue inventory
- render JobId

## What it does

List render jobs in the queue.

## Preflight and readback

Before a queue mutation, capture this full list and retain exact JobIds, positions, settings-identifying fields, and destination filenames.
After start/cancel/delete operations, run it again and compare exact ids/status/progress. For completed jobs, locate and inspect the output artifact independently.
If concurrent queue edits are possible, refresh immediately before using a 1-based index and prefer exact JobIds.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The command is read-only but requires a current project.
- No command-specific dry-run branch exists.
- Only dictionary queue entries are included; strings or other objects are silently skipped.
- A present filename value must stringify non-empty; the original value type is returned.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent render jobs --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
