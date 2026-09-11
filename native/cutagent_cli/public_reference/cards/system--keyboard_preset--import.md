# `system keyboard-preset import`

Syntax: `cutagent system keyboard-preset import PATH [--name VALUE]`

## Search terms

- system keyboard-preset import
- Import a keyboard preset from one local file.
- system keyboard-preset import help
- system keyboard-preset import command

## What it does

Import a keyboard preset from one local file.

## Preflight and readback

Capture the active preset and ordered catalog first. After success, require `imported: true`, the exact added `presetName`, the original source `path`, `activatedByImport: true`, `previousPresetRestored: true`, one exact ordered catalog insertion, and the original preset active again.

## Public arguments and options

- `PATH` (required) — Keyboard preset file path
- `--name` (optional) — Exact imported preset name

## Boundaries and gotchas

- `--name` is optional; when omitted, the exact newly added catalog entry becomes the returned name.

## Examples

- `cutagent system keyboard-preset import --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
