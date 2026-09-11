# `version status`

Syntax: `cutagent version status [--session-id VALUE]`

## Search terms

- version status
- detect project changes
- checkpoint drift
- local Disk project status

## What it does

Check project checkpoint status.

## Do not use when

Do not assume the latest checkpoint belongs to the currently active timeline. Selection filters by project name and optional session id, not timeline name/id.

## Preflight and readback

If no baseline exists, create a checkpoint rather than treating false as unchanged; if changes matter, inspect the checkpoint and verify project content in DaVinci Resolve.

## Public arguments and options

- `--session-id` (optional) — Compare only against checkpoints for this session

## Boundaries and gotchas

- Only local Disk project libraries are supported.
- `--session-id` is optional.
- There is no special dry-run branch.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent version status --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
