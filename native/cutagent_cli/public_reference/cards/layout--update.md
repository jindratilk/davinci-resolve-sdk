# `layout update`

Syntax: `cutagent layout update NAME`

## Search terms

- layout update
- Update the current layout preset.
- layout update help
- layout update command

## What it does

Update the current layout preset.

## Do not use when

Do not infer target existence from dry-run. It emits the same save plan for missing and existing names.

## Preflight and readback

Before execution, independently inspect Workspace > Layout Presets and record whether the exact normalized name already exists. Export the existing preset if preserving it matters.
Capture current UI layout state, then run global dry-run.
Delete uniquely named test presets after evidence is captured.

## Public arguments and options

- `NAME` (required) — Layout preset name

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent layout update --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
