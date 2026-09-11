# `media delete`

Syntax: `cutagent media delete NAME [--force]`

## Search terms

- delete clip from Media Pool
- remove imported asset from project
- purge source item from bin
- delete Media Pool clip by name
- remove unused footage
- delete audio asset from DaVinci Resolve
- unlink timeline item from Media Pool source
- remove project media reference

## What it does

Delete a clip from the media pool.

## Do not use when

Use `timeline items delete`, a clip delete command, or a ripple-delete command when the requested object is a timeline occurrence; `media delete` targets the source object in the Media Pool. Do not use this as disk cleanup: it does not remove the source file. Do not delete a used source when the intended result is to keep all timeline occurrences online; first identify dependents and choose relink, replace, or deliberate timeline cleanup.

## Preflight and readback

Search exact name across the Media Pool, record folder and source path, and inspect timelines for dependent items. In machine/JSON mode supply `--force` only after that dependency check; use `--dry-run` to confirm the parsed target without mutating. After deletion, require exact Media Pool search to return an empty array and inspect every affected timeline track.

## Public arguments and options

- `NAME` (required) — Clip name
- `--force/-f` (optional, default: `false`)

## Boundaries and gotchas

- JSON/machine mode requires `--force`; without it the command refuses the destructive action.
- `--dry-run` returns before this force check and before connecting to DaVinci Resolve.
- The command deletes only the Media Pool object from the open project.
- If that folder contains duplicate exact names, the first is chosen silently.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent media delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
