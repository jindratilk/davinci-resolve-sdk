# `timeline track lock`

Syntax: `cutagent timeline track lock TRACK_TYPE INDEX`

## Search terms

- lock timeline track
- protect track from edits
- track locked readback
- lock video audio subtitle
- prevent timeline item movement
- timeline track management

## What it does

Lock a track.

## Do not use when

Do not use this to disable/mute, hide, delete, or make a project-level checkpoint.
Do not use global `--dry-run` as a preview.

## Preflight and readback

Before execution, activate and save the intended timeline; freshly list tracks; verify type, one-based index, name, item count, and current lock state; and understand which later operations will be blocked by the lock. Avoid an ordinary valid dry-run.
Remember to unlock explicitly when the protected workflow is finished.

## Public arguments and options

- `TRACK_TYPE` (required)
- `INDEX` (required)

## Boundaries and gotchas

- Index must be an integer at least 1.
- Unlike enabled-state changes, lock changes do not switch UI pages.
- Locking a track can cause later clip/item operations to skip or fail; the command does not enumerate those downstream effects.
- It does not save the project.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline track lock --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
