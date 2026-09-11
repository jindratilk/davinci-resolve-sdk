# `system keyboard-preset delete`

Syntax: `cutagent system keyboard-preset delete NAME [--force]`

## Search terms

- system keyboard-preset delete
- Delete one inactive keyboard preset.
- system keyboard-preset delete help
- system keyboard-preset delete command

## What it does

Delete one inactive keyboard preset.

## Do not use when

Do not delete the active preset. Load another exact preset first.

## Preflight and readback

Capture the current preset and full ordered catalog before deletion. After success, require `deleted: true`, the target absent exactly once, every unrelated catalog entry preserved in order, and the same active preset.

## Public arguments and options

- `NAME` (required) — Exact preset name
- `--force/-f` (optional, default: `false`) — Confirm deletion

## Boundaries and gotchas

- Machine mode requires `--force`; interactive mode prompts without it.
- Recovery runs only when readback proves the exact target alone is missing and all unrelated global state still matches the baseline.

## Examples

- `cutagent system keyboard-preset delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
