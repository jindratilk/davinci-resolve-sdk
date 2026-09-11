# `fusion mask polygon`

Syntax: `cutagent fusion mask polygon POINTS`

## Search terms

- add polygon mask Fusion
- Fusion PolylineMask points
- create triangle mask
- arbitrary point mask Fusion
- polygon mask empty spline
- Polygon1Polyline BezierSpline
- polygon command false success
- connect polygon EffectMask
- polygon mask auto-connect
- validate x,y point list
- polygon one point accepted
- mask current Fusion comp

## What it does

Add a polygon mask.

## Do not use when

It reports success while discarding the requested points.
Do not run against an ambiguous current composition. There is no project, timeline, clip, track, record-frame, composition-index, or existing-mask selector.
Do not use one or two points as a meaningful polygon. The CLI does not enforce a geometrically valid minimum and can report success for a single point.
Do not assume the created mask is orphaned.
Use explicit roto/paint/tracker tooling for animated or tracked freeform work.

## Preflight and readback

Before execution, verify `status`, `fusion comp current`, and `fusion tool list`; export the composition to preserve the original topology.
Validate the point string with dry-run. Every point must be `x,y`, pairs must be separated by semicolons, and the whole shell argument should be quoted so semicolons are not interpreted as command separators.
Independently require at least three suitable points and intentional normalized coordinates; the CLI performs neither check.
Verify that the BezierSpline keyframe contains actual point records rather than an empty `Polyline {}`.
Export a representative frame and compare it with baseline.
For cleanup, delete polygon masks in reverse chain order.

## Public arguments and options

- `POINTS` (required) — Points as 'x,y;x,y;...'

## Boundaries and gotchas

- The positional points argument must be shell-quoted because it contains semicolons.
- The command cannot report whether the result is orphaned, image-connected, or chained.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion mask polygon --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
