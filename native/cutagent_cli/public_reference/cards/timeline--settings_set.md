# `timeline settings-set`

Syntax: `cutagent timeline settings-set KEY VALUE`

## Search terms

- set timeline setting
- change timeline frame rate
- set timeline resolution
- change render cache mode
- use custom timeline settings

## What it does

Set a timeline setting.

## Do not use when

Do not pass global `--dry-run` expecting safety.
Do not change frame rate, resolution, cache mode, or custom-settings state without a project checkpoint and understanding DaVinci Resolve's constraints. Some settings are immutable after timeline creation, interdependent, or can affect playback/render behavior.
Do not use arbitrary guessed keys/values.

## Public arguments and options

- `KEY` (required)
- `VALUE` (required)

## Boundaries and gotchas

- Both key and value are required positional strings.
- It requires an active timeline and has no `--timeline` selector.
- Key validation trims outer whitespace but remains case-sensitive.
- Non-numeric string comparison is exact after trimming and case-sensitive.
- The command does not expose allowed values, setting type, timeline name, dependent setting changes, project-level settings, restart requirements, or UI/render proof.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`

## Examples

- `cutagent timeline settings-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
