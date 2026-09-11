# `color page sat-curve-set`

Syntax: `cutagent color page sat-curve-set [CLIP_NAME] [--input-sat VALUE] [--input-lum VALUE] [--output-sat VALUE] [--saturation VALUE] [--lum VALUE] [--mode VALUE] [--points VALUE] [--require-render-proof]`

## Search terms

- Sat vs Sat curve
- Sat vs Lum curve
- Lum vs Sat curve
- boost only already saturated colors
- reduce saturation in highlights
- desaturate shadows with a curve
- change luminance by source saturation
- saturation selective color curve
- add multiple saturation curve control points
- tame highly saturated colors
- increase saturation by brightness
- Color page custom saturation curve

## What it does

Set a Color Page saturation curve point using project and rendered-frame proof.

## Do not use when

Use `color page sat-curve-spline-set` when the request specifically belongs to that narrower multi-point spline interface; it requires `--points`, is setup-only, and does not perform the default rendered-frame proof provided here. Use `color page hue-curve-set` for Hue vs Hue, Hue vs Sat, or Hue vs Lum isolation—the input axis there is hue, not saturation or luminance. Use `color page primary-set --sat` for a uniform whole-image saturation change, and use HDR-zone controls when the user wants tonal-zone grading rather than a continuous Lum vs Sat curve.

## Preflight and readback

Decide which axis is the selector (`sat` or `lum`) and which axis is changed; then preview the exact mode/values. Review the exported frames visually: a nonzero pixel count proves an effect, not that the curve shape is aesthetically correct. With `--setup-only`, perform a later render/frame export before reporting a visible grade.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--input-sat` (optional) — Saturation curve GUI Input Sat value (0..1)
- `--input-lum` (optional) — Lum vs Sat GUI Input Lum value (0..1)
- `--output-sat` (optional) — Sat vs Sat GUI Output Sat value (0..2)
- `--saturation` (optional) — Lum vs Sat GUI Saturation value (0..2)
- `--lum` (optional) — Sat vs Lum GUI Lum value (0..2)
- `--mode` (optional, default: `"sat-vs-sat"`) — Saturation curve mode: sat-vs-sat, sat-vs-lum, or lum-vs-sat
- `--points` (optional) — Multi-point saturation curve pairs as "input,value;input,value"
- `--require-render-proof/--setup-only` (optional, default: `true`) — Export before/after Color Page frames and fail unless rendered pixels change

## Boundaries and gotchas

- There is no `--node` option.
- This can affect a wider saturation/luminance range than the named input alone suggests.
- `--points` requires 2–32 entries in `input,value;input,value` form.
- Inputs must be strictly increasing—duplicates and descending entries fail—and both input domains are 0..1 while all output/lum/saturation domains are 0..2.
- `--points` cannot be mixed with any single-pair flag, even an otherwise irrelevant flag for another mode.
- Mode-specific flag names are not interchangeable: `sat-vs-sat` needs `--input-sat` plus `--output-sat`; `sat-vs-lum` needs `--input-sat` plus `--lum`; `lum-vs-sat` needs `--input-lum` plus `--saturation`.
- It does not create an initial grade or missing node.
- Default `--require-render-proof` captures a before frame before closing the project and an after frame following reopen.
- Name-only targeting is ambiguous when multiple timeline items share the same clip name; no track/index disambiguator is exposed.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page sat-curve-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
