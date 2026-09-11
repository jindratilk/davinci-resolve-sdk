# `clip keyframe delete`

Syntax: `cutagent clip keyframe delete PROPERTY_NAME FRAME [--clip VALUE]`

## Search terms

- delete clip Inspector keyframe
- remove ZoomX animation point
- clear opacity keyframe at frame
- remove transform animation point
- delete clip volume automation point
- remove one crop keyframe
- clean up timeline item keyframe
- delete keyframe by record frame

## What it does

Delete a keyframe.

## Do not use when

Use `clip keyframe get` for inspection, `set-interpolation` when the point should remain, and static transform/property commands when the base value—not an animation point—must change. Use Fusion keyframe deletion for Fusion tools and Fairlight automation commands for track curves. Do not use this to clear an entire unknown curve without first enumerating every exact frame.

## Preflight and readback

After deletion, require the returned count and decoded list to omit only that frame, verify the same project/timeline reopened, and inspect/render neighboring interpolation behavior. After the last deletion, confirm count 0 rather than assuming a success message cleared the entry.

## Public arguments and options

- `PROPERTY_NAME` (required) — Property name
- `FRAME` (required) — Record frame position
- `--clip` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- This removes only the animation point.
- It does not report or change the held/base Inspector value DaVinci Resolve uses after the curve disappears.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent clip keyframe delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
