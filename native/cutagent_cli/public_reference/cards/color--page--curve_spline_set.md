# `color page curve-spline-set`

Syntax: `cutagent color page curve-spline-set [CLIP_NAME] [--channel VALUE] [--points VALUE]`

## Search terms

- set one custom curve spline
- freeform Y curve
- single-channel curve points
- red curve spline
- green custom curve shape
- master luma custom curve

## What it does

Runs the public `color page curve-spline-set` CutAgent command.

## Do not use when

Use `curve-points-set` when several channels should be written atomically or rendered-frame proof is required, and `curve-set` when moving the high endpoint scalar rather than shaping the curve. Use hue/saturation curve commands for Hue-vs-Hue/Sat/Lum families.

## Preflight and readback

Before running, inspect/export the active grade, normalize/sort points and confirm the selected channel alias.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--channel` (optional, default: `"Y"`) — Requested curve channel: Y, R, G, or B
- `--points` (optional) — Requested freeform curve points

## Boundaries and gotchas

- `--points` is mandatory.
- “Spline” does not mean exact pin/handle preservation here.
- Unlike `curve-points-set`, this command has no `--require-render-proof`/`--setup-only` toggle.
- Only one channel is written per invocation.

## Examples

- `cutagent color page curve-spline-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
