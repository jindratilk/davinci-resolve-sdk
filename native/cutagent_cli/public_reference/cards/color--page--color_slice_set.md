# `color page color-slice-set`

Syntax: `cutagent color page color-slice-set [CLIP_NAME] [--vector VALUE] [--hue VALUE] [--saturation VALUE] [--luma VALUE]`

## Search terms

- ColorSlice vector adjustment
- change blue slice
- skin vector hue
- make one color more saturated
- Color Slice density
- adjust red yellow green cyan blue magenta slice
- isolate and tune color family

## What it does

Set Color Page ColorSlice vector controls through the interface.

## Do not use when

Use `color page hue-curve-set` for a hue-selected curve with explicit curve points, `color page qualifier-*` when a matte/isolation is needed, and primary/RGB-mixer controls for global color changes. Use `color page color-slice-set` only for the current GUI clip; the clip argument does not navigate.

## Preflight and readback

Before running, place the intended clip under the playhead, verify `clip current`, open/allow the Color page, and grant both Accessibility and Screen Recording to the CutAgent CLI host. Record the vector's current values if the operation must be reversible.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--vector` (optional, default: `"red"`) — ColorSlice vector: red, skin, yellow, green, cyan, blue, or magenta
- `--hue` (optional) — Requested Color Slice hue
- `--saturation` (optional) — Requested Color Slice saturation adjustment
- `--luma` (optional) — Requested Color Slice luma adjustment

## Boundaries and gotchas

- Accepted ranges differ: Hue is -0.10..0.10 and rounded to two decimals, Saturation is 0..200, and `--luma` is Density 0..100.
- Duplicate names do not provide navigation semantics.
- At least one of hue/saturation/luma is required.
- Omitting all three is a validation error even though `--vector` has a default.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page color-slice-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
