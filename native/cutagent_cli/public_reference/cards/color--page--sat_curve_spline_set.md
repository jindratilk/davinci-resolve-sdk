# `color page sat-curve-spline-set`

Syntax: `cutagent color page sat-curve-spline-set [CLIP_NAME] [--mode VALUE] [--points VALUE]`

## Search terms

- draw a Sat vs Sat spline
- exact saturation curve points
- multi-point Lum vs Sat curve
- multi-point Sat vs Lum curve
- saturation curve control points
- shape saturation response curve
- tame saturated colors with several points
- desaturate highlights along a spline
- change brightness according to saturation
- replace Color page Sat/Lum curve
- set curve points without render proof

## What it does

Runs the public `color page sat-curve-spline-set` CutAgent command.

## Do not use when

Use `color page hue-curve-spline-set` when the input selector is hue, not saturation/luminance. Use `color page primary-set --sat` for uniform saturation, and do not use this command for independently editable GUI Bezier handles: that control surface is not implemented even though the option help mentions “points/handles.”

## Preflight and readback

Before writing, inspect `color page read` for the exact clip's active grade version and current Sat/Lum curves, record every existing point because the selected curve will be replaced, and confirm node 1 is the intended correction node.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--mode` (optional, default: `"sat-vs-sat"`) — Requested Sat/Lum curve mode
- `--points` (optional) — Requested exact GUI spline points/handles

## Boundaries and gotchas

- `--points` is mandatory.
- Input coordinates must be finite, in 0..1, and strictly increasing.
- Duplicate X positions and descending pairs fail.
- Output saturation/luminance values must be finite and in 0..2.
- Empty semicolon segments are discarded before counting, so a trailing semicolon is harmless but does not add a point.
- Only X/Y points are represented; independent left/right handles, curve tension and interpolation type cannot be supplied.
- It does not inspect the Color-page curve widget or rendered pixels.
- Duplicate-named timeline items can make the intended active grade ambiguous.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page sat-curve-spline-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
