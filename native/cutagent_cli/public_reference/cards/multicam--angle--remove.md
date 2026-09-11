# `multicam angle remove`

Syntax: `cutagent multicam angle remove --angle VALUE [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--force]`

## Search terms

- multicam angle remove
- Remove a multicam angle.
- multicam angle remove help
- multicam angle remove command

## What it does

Remove a multicam angle.

## Do not use when

Do not use when temporary hiding is sufficient; use `set-enabled`. Do not remove an angle from a two-angle multicam because at least two video angles must remain. Check timeline selector implications before removing a used angle.

## Preflight and readback

Checkpoint and inspect item IDs, selector usage, and angle order. After mutation require exact track/item deletion, paired video/audio reindexing, minimum-angle enforcement, and reopen readback.

## Public arguments and options

- `--angle` (required)
- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--force/-f` (optional, default: `false`)

## Boundaries and gotchas

- `--angle` is one-based.

## Examples

- `cutagent multicam angle remove --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
