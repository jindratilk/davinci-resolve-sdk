# `clip cache-set`

Syntax: `cutagent clip cache-set [CLIP] [--type VALUE] --mode VALUE`

## Search terms

- set clip cache mode explicitly
- restore Fusion cache to auto
- enable Fusion output cache
- disable color output cache
- force or auto cache one clip

## What it does

Update clip cache state.

## Do not use when

Use `clip cache-state` for read-only inspection and `clip cache` when only a boolean enable/disable interface is desired. Do not use this as a wait-until-cached operation.

## Preflight and readback

Confirm the exact item and global cache/storage readiness. After setting, inspect returned actual/requested fields, then separately verify the visible cache indicator and eventual playback/render result.

## Public arguments and options

- `CLIP` (optional) — Clip name (current clip when omitted)
- `--type` (optional, default: `"color"`) — Cache type: color or fusion
- `--mode` (required) — enable|disable|auto

## Boundaries and gotchas

- `auto` is valid only for Fusion.
- `--type color --mode auto` fails validation before connecting; the error explicitly lists color enable/disable and Fusion's additional auto mode.
- Color and Fusion modes are independent; changing one does not normalize the other.
- The shared name/current resolver has first-video priority and no occurrence selector, so duplicate names are unsafe.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent clip cache-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
