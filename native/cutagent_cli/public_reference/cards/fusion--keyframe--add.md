# `fusion keyframe add`

Syntax: `cutagent fusion keyframe add TOOL_NAME INPUT_NAME FRAME VALUE`

## Search terms

- add Fusion keyframe
- animate Fusion input
- BezierSpline keyframe
- add node animation point
- MediaIn keyframe
- keyframe add false positive
- inspect Fusion keyframes
- restore animated Fusion input

## What it does

Add a Fusion keyframe.

## Do not use when

Do not assume every Fusion input supports spline animation.
Do not use guessed tool/input names. Open the correct Fusion composition and inspect `fusion tool list` plus `fusion tool inputs` first.
Do not use this when the active composition is ambiguous. The command has no clip, track, composition-index, or timeline-item selector.
Preserve the original constant/animation state before mutation.

## Preflight and readback

Before execution, confirm the active page/comp, timeline, clip, tool name, input ID, current frame, current input value, and existing keyframe list.
Run dry-run and verify the exact tool/input/frame/value text. Dry-run does not parse the value, connect, find the tool, or inspect animation support.
Treat identical values across frames with an empty keyframe list as a constant assignment, not successful animation.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name
- `INPUT_NAME` (required) — Input name
- `FRAME` (required) — Frame number
- `VALUE` (required) — Value to set

## Boundaries and gotchas

- All four arguments are required; there are no command-specific options.
- Frame has no minimum or composition-range validation in the command.
- Dry-run returns only a message, not action/tool/input/frame/value fields.
- `fusion keyframe clear --force` did not remove that spline modifier.

## Stable public error codes

- `API_CALL_FAILED`
- `MISSING_ARGUMENT`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion keyframe add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
