# `timeline settings`

Syntax: `cutagent timeline settings [KEY]`

## Search terms

- timeline frame rate setting
- timeline resolution settings
- list DaVinci Resolve timeline configuration
- inspect active timeline properties
- get one timeline setting

## What it does

Check timeline settings.

## Do not use when

Do not use this command to change a setting; use `timeline settings-set KEY VALUE` with an explicit checkpoint and readback.
Do not assume the all-settings dictionary is stable across DaVinci Resolve versions, project modes, or timeline types.

## Preflight and readback

After execution, retain the exact key/value representation and corroborate critical FPS/resolution/cache settings in DaVinci Resolve. A null/empty single-key value is returned as data, not automatically treated as an error.

## Public arguments and options

- `KEY` (optional) — Specific setting key

## Boundaries and gotchas

- There is no `--timeline` option; activate another timeline separately.
- The command does not return project-level settings, preset inheritance, whether a value is editable, acceptable values, or source/default provenance.
- It does not compare timeline and project settings.
- Global `--dry-run` has no special branch and still connects and reads.
- The command does not mutate timeline state, current timeline, or settings.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline settings --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
