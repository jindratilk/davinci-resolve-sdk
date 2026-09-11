# `render settings-set-json`

Syntax: `cutagent render settings-set-json JSON_OR_FILE`

## Search terms

- render settings-set-json
- Update render settings.
- render settings-set-json help
- render settings-set-json command

## What it does

Update render settings.

## Preflight and readback

Use dry-run to verify parsing and the ordered key list.
Restore the prior preset/settings manually if any key was ignored or caused an undesirable partial change.

## Public arguments and options

- `JSON_OR_FILE` (required) — JSON object or path to a JSON file

## Boundaries and gotchas

- Dry-run lists keys in parsed insertion order.
- A dry-run of `{}` succeeds with an empty key list.
- It cannot determine whether DaVinci Resolve ignored some keys while accepting others.
- Changing format/codec through arbitrary keys does not use the curated selector resolution in `render settings-set`.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render settings-set-json --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
