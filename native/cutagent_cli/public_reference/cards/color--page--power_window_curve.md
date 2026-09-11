# `color page power-window-curve`

Syntax: `cutagent color page power-window-curve [CLIP_NAME] [--node-index VALUE] [--points VALUE]`

## Search terms

- draw curved Power Window
- custom spline mask
- bezier Power Window
- freeform curved mask
- closed curve selection
- organic shape mask
- isolate irregular object with curve
- custom Color page window points
- curved vignette shape
- node-local curve window

## What it does

Update a Color Page Curve Power Window using project readback.

## Do not use when

Use `power-window-polygon` for straight-edged vertices without Curve semantics, circle/rectangle/linear/gradient commands for their simpler editable controls, and Magic Mask for semantic subject isolation. Use `power-window-track` after creation for motion.

## Preflight and readback

Save a grade checkpoint and reference matte/render. Supply ordered perimeter vertices in normalized viewer/image coordinates and avoid self-intersections unless intentional. Track separately if required.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index; create/use an empty local node for secondaries
- `--points` (optional) — Closed Curve Power Window points as normalized 'x,y;x,y;x,y' pairs

## Boundaries and gotchas

- At least three points are required, but there is no validation for duplicate vertices, winding, self-intersection, tiny area or maximum point count.
- Omitting `--points` does not mean “leave points unchanged”; it replaces/creates with the built-in four-point default shape.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page power-window-curve --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
