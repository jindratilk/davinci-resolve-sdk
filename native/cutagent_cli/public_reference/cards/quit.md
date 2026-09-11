# `quit`

Syntax: `cutagent quit [--force]`

## Search terms

- quit DaVinci Resolve
- close DaVinci Resolve application
- quit process verification
- embedded fuscript cleanup
- quit timeout
- force quit confirmation
- unsaved changes warning
- CutAgent script host cleanup

## What it does

Quit DaVinci Resolve.

## Do not use when

Do not quit while unsaved project changes, renders, background jobs, uploads, or collaboration sync are active.
Do not use this merely to close the current project; use `project close`.
Do not supply `--force` until application exit is explicitly intended. This can terminate DaVinci Resolve and embedded script hosts.

## Preflight and readback

Before execution, save/export/archive as needed, stop/verify render and background jobs, record current project/timeline, and ensure no other user depends on the app session.
Restart and open the project to verify persistence.

## Public arguments and options

- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- Exact help is `cutagent quit [--force]`.
- `--force` has no effect under global dry-run.
- There is no `--timeout` option.

## Stable public error codes

- `CONFIRMATION_REQUIRED`
- `INVALID_OPTION`

## Examples

- `cutagent quit --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
