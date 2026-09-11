# `color page hue-curve-spline-set`

Syntax: `cutagent color page hue-curve-spline-set [CLIP_NAME] [--mode VALUE] [--points VALUE]`

## Search terms

- set Hue curve spline
- exact Hue vs Hue points
- multi-point hue curve
- Hue vs Sat spline
- Hue vs Lum control points
- custom hue curve coordinates

## What it does

Runs the public `color page hue-curve-spline-set` CutAgent command.

## Do not use when

Use `hue-curve-set` when a single cyclic shift is intended or when automatic rendered proof should accompany a multi-point write. Use conventional Custom Curves commands for Y/R/G/B, saturation-curve commands for Sat/Lum input axes, and a GUI/manual workflow if Bezier handles must be authored.

## Preflight and readback

Afterward, require point-count and per-point decoded readback, inspect the curve panel for interpolation/wrap behavior, and render a frame containing the targeted hues because the command provides no pixel proof.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--mode` (optional, default: `"hue-vs-hue"`) — Requested Hue curve mode
- `--points` (optional) — Requested exact GUI spline points/handles

## Boundaries and gotchas

- Unlike `hue-curve-set`, there is no `--require-render-proof`/`--setup-only` switch.

## Examples

- `cutagent color page hue-curve-spline-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
