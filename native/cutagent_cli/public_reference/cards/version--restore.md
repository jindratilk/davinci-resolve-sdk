# `version restore`

Syntax: `cutagent version restore CHECKPOINT_ID [--session-id VALUE]`

## Search terms

- restore project checkpoint
- reopen checkpoint timeline
- checkpoint disaster recovery
- version checkpoint recovery

## What it does

Restore a project checkpoint.

## Do not use when

Do not restore merely because dry-run succeeds.

## Public arguments and options

- `CHECKPOINT_ID` (required) — Checkpoint id
- `--session-id` (optional) — Require the checkpoint to belong to this CutAgent session id

## Boundaries and gotchas

- `--session-id` is optional.
- Omitting `--session-id` disables chat/session ownership checking.
- A blank or whitespace-only supplied session id behaves like no session guard.
- There is no interactive confirmation or `--force`.
- Dry-run merely echoes checkpoint/session identifiers and a generic intention.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent version restore --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
