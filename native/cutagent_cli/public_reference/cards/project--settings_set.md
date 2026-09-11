# `project settings-set`

Syntax: `cutagent project settings-set KEY VALUE`

## Search terms

- set project setting
- timeline frame rate project setting
- colorSpaceTimeline alias
- DaVinci Wide Gamut Intermediate
- project setting readback
- separateColorSpaceAndGamma
- no-op setting write

## What it does

Set a project setting.

## Do not use when

Do not change frame rate, resolution, or color management without saving/exporting and understanding downstream timeline/media effects.
Do not use combined DaVinci Wide Gamut/Intermediate while `separateColorSpaceAndGamma` is `"1"`; first set that mode to `0`.
Do not assume value strings are fully validated during dry-run.

## Preflight and readback

Run connected dry-run and review previous/requested/normalized values, alias metadata, key validation, and changed status.

## Public arguments and options

- `KEY` (required) — Setting key
- `VALUE` (required) — Setting value

## Boundaries and gotchas

- Both key and value are required positional strings.
- There is no `--force` or confirmation.
- A current project is required before any dry-run output.
- Dict response validates exact/case-sensitive key and returns sorted available keys on failure.
- Dry-run occurs after key and combined-color validation.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`
- `MISSING_ARGUMENT`

## Examples

- `cutagent project settings-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
