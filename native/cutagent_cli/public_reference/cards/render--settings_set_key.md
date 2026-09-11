# `render settings-set-key`

Syntax: `cutagent render settings-set-key KEY VALUE`

## Search terms

- set one render setting
- arbitrary Deliver setting
- typed setting from CLI text
- FrameRate numeric setting

## What it does

Update one render setting.

## Do not use when

Do not use it for multiple related keys that must be reviewed together; use a carefully validated JSON object.

## Preflight and readback

Quote shell-sensitive JSON and strings explicitly, and avoid surrounding whitespace unless it is intentionally part of the value.

## Public arguments and options

- `KEY` (required)
- `VALUE` (required)

## Boundaries and gotchas

- Both positional arguments are required.
- An explicitly empty key succeeds in dry-run.
- Value coercion does not strip whitespace.
- Case-insensitive exact `true`/`false` becomes a boolean.
- Case-insensitive exact `null`/`none` becomes null.
- Dry-run performs coercion before returning.
- Dry-run does not validate the key/value against DaVinci Resolve and does not connect.
- Some valid write-only or version-specific keys may not appear in normal readback.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent render settings-set-key --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
