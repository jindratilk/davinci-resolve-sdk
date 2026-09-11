# `project settings-get`

Syntax: `cutagent project settings-get [KEY]`

## Search terms

- project settings get alias
- list all project settings
- exact setting key
- timelineFrameRate project setting
- project settings dictionary
- unknown setting validation
- DaVinci Resolve project configuration

## What it does

Check project settings (all and specific key).

## Do not use when

Do not use this to mutate project settings; use `project settings-set`.
Do not pass `--key`; the key is positional.
Do not confuse project-level keys with timeline/render/application settings.

## Preflight and readback

Before execution, open the intended project and obtain exact key spelling from the full no-key result when possible.
After execution, preserve the returned value/type as pre-state before any settings change. For unknown dict keys, use the returned sorted available-key list.

## Public arguments and options

- `KEY` (optional) — Setting key to get

## Boundaries and gotchas

- A current project is required.
- Key matching is exact/case-sensitive.
- Global dry-run has no separate branch.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`
- `VALIDATION_ERROR`

## Examples

- `cutagent project settings-get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
