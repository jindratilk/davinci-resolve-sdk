# `clip keyframe add`

Syntax: `cutagent clip keyframe add PROPERTY_NAME FRAME VALUE [--clip VALUE]`

## Search terms

- animate clip Inspector property
- add ZoomX keyframe
- keyframe opacity on timeline clip
- animate pan tilt crop
- add clip volume automation point
- set transform value at record frame
- create Inspector animation
- add audio pan keyframe
- animate timeline item without Fusion

## What it does

Add a keyframe on a timeline item property.

## Do not use when

Use `clip transform` for one static value with no animation, Fusion tool/keyframe commands for node controls, Fairlight track automation for track-level mixing, and speed-ramp commands for retime points. Use `clip keyframe set-interpolation` to alter the curve of an existing point and `delete` to remove one. Do not use this on cloud/PostgreSQL project libraries or when a real DaVinci Resolve post-reopen Viewer/render check cannot be performed for a production edit.

## Preflight and readback

Add one point at a frame satisfying `start <= frame < end`.

## Public arguments and options

- `PROPERTY_NAME` (required) — Property name (e.g., ZoomX, Pan, Opacity)
- `FRAME` (required) — Record frame position
- `VALUE` (required) — Property value
- `--clip` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- Adding at an already-keyframed local frame replaces that point rather than creating a duplicate; all other frames for that property remain.
- ZoomX/ZoomY are synchronized only when the counterpart has no independent curve or exactly matched the pre-change curve.
- There is no safe dry-run branch in this command.

## Examples

- `cutagent clip keyframe add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
