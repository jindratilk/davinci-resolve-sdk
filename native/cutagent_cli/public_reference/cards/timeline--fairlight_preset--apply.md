# `timeline fairlight-preset apply`

Syntax: `cutagent timeline fairlight-preset apply NAME`

## Search terms

- apply Fairlight preset
- current timeline audio preset
- Fairlight mix preset
- partial Fairlight preset support
- unguarded preset apply

## What it does

Apply a Fairlight preset to the current timeline.

## Do not use when

Prefer `fairlight preset apply NAME` when catalog-checked readiness behavior is required.
Do not use this command to apply GUI Equalizer presets merely because their names are visible in DaVinci Resolve.

## Preflight and readback

Record relevant mixer, routing, EQ, dynamics, and plugin state for manual comparison.

## Public arguments and options

- `NAME` (required) — Fairlight preset name

## Boundaries and gotchas

- If neither method is callable, the error reports both required methods and attempts.
- The command does not automatically save the project.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`

## Examples

- `cutagent timeline fairlight-preset apply --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
