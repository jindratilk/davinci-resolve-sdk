# `system keyframe-mode set`

Syntax: `cutagent system keyframe-mode set MODE`

## Search terms

- set keyframe mode
- show all keyframes
- color keyframes only
- sizing keyframes only
- global keyframe filter
- keyframe mode integer mapping
- Color page keyframe display
- system keyframe setting

## What it does

Set the current keyframe mode.

## Do not use when

Do not confuse this global/application display mode with clip keyframe interpolation, retime keyframe behavior, or Fairlight automation.
Do not change the mode without recording the previous value when UI state matters.
Do not expect the command to verify the visible UI or any keyframe data.

## Preflight and readback

Before execution, run `system keyframe-mode get` and record the raw previous value. Ensure changing the global mode is acceptable for the current DaVinci Resolve session.
Use one exact lowercase token. Dry-run validates the token and shows the intended name without connecting.

## Public arguments and options

- `MODE` (required) — all|color|sizing

## Boundaries and gotchas

- The command does not modify keyframe values themselves.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent system keyframe-mode set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
