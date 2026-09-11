# `fusion nested-text batch`

Syntax: `cutagent fusion nested-text batch --batch VALUE`

## Search terms

- batch nested Fusion text
- nested timeline JSON batch
- partial nested text failure
- legacy explanation batch
- restore outer timeline batch
- nested text dry-run connects
- compound text batch verification

## What it does

Update nested Fusion text templates.

## Do not use when

Do not use this when all updates must be atomic. Earlier entries can remain changed when a later entry fails.
It connects and may open/switch nested timelines before restoring them.
Do not batch guessed nested item names.
Do not use it without capturing original text and original timeline state for every entry.

## Preflight and readback

Before execution, validate batch JSON and independently inventory every outer target, nested timeline, candidate text item, original header/body value, and expected current-timeline restoration.
Use explicit nested clip names and unique outer selectors. Preserve an inverse batch containing the original strings.
Run dry-run and still monitor DaVinci Resolve.
Compare counts with the intended entry count.
Render representative output for every visually distinct template. If any row fails, decide whether to roll back successful rows using the inverse batch; do not retry the whole batch blindly.

## Public arguments and options

- `--batch/--input` (required) — Batch JSON path

## Boundaries and gotchas

- `--batch TEXT` / `--input TEXT` is required.
- After structural validation, the command connects even in dry-run.
- Track and record frame must be paired; clip is mutually exclusive with them.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion nested-text batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
