# `color page hue-curve-set`

Syntax: `cutagent color page hue-curve-set [CLIP_NAME] [--input-hue VALUE] [--mode VALUE] [--hue-rotate VALUE] [--saturation VALUE] [--lum-gain VALUE] [--points VALUE] [--require-render-proof]`

## Search terms

- Hue vs Hue curve
- Hue vs Saturation
- Hue vs Luminance
- rotate one hue
- change saturation by hue
- brighten a color range
- set hue curve points
- adjust color family curve

## What it does

Set Color Page hue curve point(s) using project and rendered-frame proof.

## Do not use when

Do not use the single-point form expecting a localized pin: its generated curve uses one constant y across seven wrap positions, so it behaves as a global mode-specific shift shaped around a cyclic seam.

## Preflight and readback

For points, sort strictly and keep the mode-specific output domain.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--input-hue` (optional) — Hue curve GUI Input Hue value (0..720)
- `--mode` (optional, default: `"hue-vs-hue"`) — Hue curve mode: hue-vs-hue, hue-vs-sat, or hue-vs-lum
- `--hue-rotate` (optional) — Hue vs Hue GUI Hue Rotate value (-180..180)
- `--saturation` (optional) — Hue vs Sat GUI Saturation value (0..2)
- `--lum-gain` (optional) — Hue vs Lum GUI Lum Gain value (0..2)
- `--points` (optional) — Multi-point Hue curve pairs as "input_hue,value;input_hue,value"
- `--require-render-proof/--setup-only` (optional, default: `true`) — Export before/after Color Page frames and fail unless rendered pixels change

## Boundaries and gotchas

- It does not create one localized control point.
- `--input-hue` positions the cyclic structure/seam while the requested rotate/saturation/lum value is constant across those points.
- `--points` cannot be combined with any single-point option.
- Only the first grade node is targeted, and an existing grade version/param section is required.
- A curve targeting hues absent at that frame can be structurally correct but fail proof; choose the proof frame carefully or use setup-only and perform a more suitable manual render.

## Examples

- `cutagent color page hue-curve-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
