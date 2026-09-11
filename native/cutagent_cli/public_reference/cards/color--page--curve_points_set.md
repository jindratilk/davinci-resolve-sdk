# `color page curve-points-set`

Syntax: `cutagent color page curve-points-set [CLIP_NAME] [--all-points VALUE] [--y VALUE] [--red VALUE] [--green VALUE] [--blue VALUE] [--require-render-proof]`

## Search terms

- set custom curve points
- make S curve
- edit Y curve shape
- RGB channel curve control points
- normalized custom curves
- add midpoint to Color curve
- linked Y RGB curve points

## What it does

Set Color Page Custom Curves control points using project and rendered-frame proof.

## Preflight and readback

Before running, sort every specification by increasing x, keep x/y in 0..1, export the grade, and calculate whether forced identity endpoints are acceptable. Inspect the actual Custom Curves panel and a frame with tonal variation; a solid frame can hide curve-shape mistakes.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--all-points` (optional) — Set linked Y/R/G/B Custom Curves points as 'x,y;x,y' normalized pairs
- `--y` (optional) — Set Y Custom Curves points as 'x,y;x,y' normalized pairs
- `--red` (optional) — Set Red Custom Curves points as 'x,y;x,y' normalized pairs
- `--green` (optional) — Set Green Custom Curves points as 'x,y;x,y' normalized pairs
- `--blue` (optional) — Set Blue Custom Curves points as 'x,y;x,y' normalized pairs
- `--require-render-proof/--setup-only` (optional, default: `true`) — Export before/after Color Page frames and fail unless rendered pixels change

## Boundaries and gotchas

- User-provided y values at x=0 or x=1 do not replace the forced identity endpoints: interpolation returns 0 at the low end and 1 at the high end.
- Inputs must be finite, within 0..1 and sorted by x.
- It does not preserve every manually chosen curve-panel linkage/display state.
- Only the first grade node is targeted, and an existing grade parameter section is required.

## Examples

- `cutagent color page curve-points-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
