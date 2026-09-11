# `timeline track unlock`

Syntax: `cutagent timeline track unlock TRACK_TYPE INDEX`

## Search terms

- unlock timeline track
- allow edits on track
- track unlocked readback
- unlock video audio subtitle
- remove edit protection
- timeline track management

## What it does

Unlock a track.

## Do not use when

Do not use this to enable/unmute, show, delete, or restore a track.
Do not unlock a protected track casually before broad or index-based edits; subsequent operations can now move, trim, replace, or delete its items.
Do not use global `--dry-run` as a preview. The command lacks a dry-run branch and can perform the real unlock.

## Preflight and readback

Before execution, activate and save the intended timeline; freshly list tracks; verify type, one-based index, name, item count, current lock state, and why the protection can be removed; and avoid a normal valid dry-run.
Perform only the intended edit and re-lock the track explicitly if the workflow still requires protection.

## Public arguments and options

- `TRACK_TYPE` (required)
- `INDEX` (required)

## Boundaries and gotchas

- Index must be an integer at least 1.
- The command does not track why the lock existed or automatically restore it after later work.
- It does not save the project.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline track unlock --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
