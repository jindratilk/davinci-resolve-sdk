# `system keyframe-mode get`

Syntax: `cutagent system keyframe-mode get`

## Search terms

- get keyframe mode
- all color sizing keyframes
- current DaVinci Resolve keyframe filter
- global keyframe mode
- keyframe display mode integer
- system keyframe setting
- Color page keyframe mode
- inspect keyframe mode

## What it does

Read the current keyframe mode.

## Do not use when

Do not confuse this global/application keyframe mode with keyframe interpolation, retime keyframe behavior, clip animation data, or Fairlight automation mode.
Do not assume an arbitrary returned value has been normalized to the documented three modes.
Do not use this as proof of a visible UI state without comparing the relevant DaVinci Resolve panel.

## Preflight and readback

Before execution, ensure the embedded bridge is running.
Interpret normal integer values using the paired setter mapping and preserve unknown values verbatim for diagnostics.
After a `system keyframe-mode set`, rerun this getter and compare both numeric value and visible UI selection.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- It does not indicate which page or panel owns the visible setting.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent system keyframe-mode get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
