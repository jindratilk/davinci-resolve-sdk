# `project settings`

Syntax: `cutagent project settings [KEY]`

## Search terms

- get project settings
- all DaVinci Resolve project settings
- timeline frame rate setting
- unknown project setting
- settings dictionary
- project configuration audit

## What it does

Check project settings (all and specific key).

## Do not use when

Do not use this to change a setting; use `project settings-set`.
Do not confuse project settings with timeline settings, render settings, or app preferences.

## Preflight and readback

After all-settings output, preserve the complete mapping as the pre-state for any mutation. After key output, confirm value type/string representation before comparing or writing.

## Public arguments and options

- `KEY` (optional) — Setting key to get

## Boundaries and gotchas

- A current project is required.
- Dict-mode key membership is exact/case-sensitive.
- Global dry-run changes metadata but not execution.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent project settings --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
