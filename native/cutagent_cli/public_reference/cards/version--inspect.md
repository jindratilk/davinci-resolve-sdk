# `version inspect`

Syntax: `cutagent version inspect CHECKPOINT_ID`

## Search terms

- version inspect
- Inspect a project checkpoint.
- version inspect help
- version inspect command

## What it does

Inspect a project checkpoint.

## Do not use when

Inspect returns index metadata only.

## Public arguments and options

- `CHECKPOINT_ID` (required) — Checkpoint id

## Boundaries and gotchas

- The checkpoint id is an exact, case-sensitive string match.
- Duplicate ids in a manually edited index are not detected.
- Only dictionary entries with a string `id` survive index filtering.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent version inspect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
