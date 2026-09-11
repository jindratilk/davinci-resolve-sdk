# `render preset-update`

Syntax: `cutagent render preset-update NAME`

## Search terms

- render preset-update
- Replace an existing preset with current render settings and verify its exported content.
- render preset-update help
- render preset-update command

## What it does

Replace an existing preset with current render settings and verify its exported content.

## Do not use when

Use `render preset-save` to create a new name.

## Preflight and readback

List `render presets` and choose the exact existing name. Configure and inspect current render settings.

## Public arguments and options

- `NAME` (required) — Exact existing render preset name

## Boundaries and gotchas

- Names must be exact, non-empty and have no surrounding whitespace.
- Uses temporary owned presets for full render-context capture, verifies cleanup, and does not queue or start rendering.
- Public SDK action takes only `presetName`; prepared execution rejects changes to the target preset or current settings before writing.

## Examples

- `cutagent render preset-update --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
