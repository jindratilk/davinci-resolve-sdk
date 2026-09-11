# `fusion keyframe set`

Syntax: `cutagent fusion keyframe set TOOL_NAME INPUT_NAME FRAME VALUE`

## Search terms

- set Fusion keyframe
- BezierSpline input animation
- set keyframe numeric value
- Fusion keyframe readback
- keyframe set false positive
- MediaIn GlobalIn animation
- restore Fusion constant value

## What it does

Set a keyframe.

## Do not use when

Do not interpret the success message as proof that a time-varying keyframe exists.
Do not use it when the target comp is ambiguous. It exposes no clip, timeline-item, track, or composition-index selector.
Do not use it to set interpolation, easing, tangent handles, or spline modifiers; the command has no such options.
Do not rely on command-side whitespace validation.

## Preflight and readback

Run dry-run and verify exact argument placement. Remember that the displayed value is still raw text and that no animation support is checked.
Require different expected per-frame values and a reliable list/readback before claiming animation.
A successful clear/list pair does not prove attempted spline modifiers were removed.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name
- `INPUT_NAME` (required) — Input name
- `FRAME` (required) — Frame number
- `VALUE` (required) — Value to set

## Boundaries and gotchas

- All four arguments are required; there are no command-specific options.
- Frame has no minimum or composition-range validation.
- Dry-run does not parse the value or connect.

## Examples

- `cutagent fusion keyframe set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
