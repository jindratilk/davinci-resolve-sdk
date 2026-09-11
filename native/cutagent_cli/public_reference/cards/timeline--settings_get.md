# `timeline settings-get`

Syntax: `cutagent timeline settings-get [KEY]`

## Search terms

- explicitly get timeline setting
- inspect timeline resolution
- list active timeline settings
- read-only timeline configuration
- settings-get alias

## What it does

Check timeline settings.

## Preflight and readback

Before execution, activate the intended timeline and choose either no key for discovery or one exact case-sensitive positional key.
After execution, preserve the exact returned string/value and validate critical properties against the DaVinci Resolve UI or a second read. A successful null/empty value does not prove the setting is meaningful or available.

## Public arguments and options

- `KEY` (optional) — Specific setting key

## Boundaries and gotchas

- Specific-key validation trims outer whitespace and remains case-sensitive.
- If discovery throws, only static keys remain available.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent timeline settings-get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
