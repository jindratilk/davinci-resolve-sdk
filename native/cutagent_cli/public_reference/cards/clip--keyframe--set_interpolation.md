# `clip keyframe set-interpolation`

Syntax: `cutagent clip keyframe set-interpolation PROPERTY_NAME FRAME INTERPOLATION [--clip VALUE]`

## Search terms

- change keyframe easing
- set ZoomX keyframe Ease-In
- make clip animation Bezier
- change Inspector point to Linear
- ease out transform keyframe
- adjust opacity keyframe interpolation
- change curve type at record frame
- smooth timeline item animation

## What it does

Set interpolation type for a keyframe.

## Do not use when

Use static transform commands when no curve is desired.

## Preflight and readback

Choose one of the four canonical types and run the mutation. After reopen, require the target point's interpolation/code/flags to change while count, frame, value, and other points remain equal.

## Public arguments and options

- `PROPERTY_NAME` (required) — Property name
- `FRAME` (required) — Record frame position
- `INTERPOLATION` (required) — Linear|Bezier|Ease-In|Ease-Out
- `--clip` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- The command cannot create a keyframe.
- Requesting frame 86411 when points existed only at 86400 and 86410 returned `No keyframe found at frame` and restored the project before commit.
- There is no dry-run branch.

## Examples

- `cutagent clip keyframe set-interpolation --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
