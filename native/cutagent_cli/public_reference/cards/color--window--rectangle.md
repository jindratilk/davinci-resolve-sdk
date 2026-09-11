# `color window rectangle`

Syntax: `cutagent color window rectangle [--clip VALUE] [--center VALUE] [--width VALUE] [--height VALUE] [--softness VALUE] [--comp VALUE]`

## Search terms

- add rectangular grading window
- create box Fusion mask
- isolate screen with rectangle
- add soft-edged color correction box
- make rectangular vignette
- mask ColorCorrector with RectangleMask
- add crop-shaped grading region
- create offscreen rectangle matte
- spotlight area with box mask
- add Fusion rectangle window
- feathered rectangular color mask

## What it does

Add a rectangular grading window using Fusion mask.

## Do not use when

Use `window attach` for an existing orphan, `detach` to preserve but bypass a window, and `reorder` when no new shape is needed.
Use a Fusion input-edit workflow for in-place changes. Do not use the rectangle command for chroma qualification or tracking; compose with the dedicated helpers after verifying the canonical chain.

## Preflight and readback

Center 0.5,0.5 is frame center; values outside 0–1 and dimensions over 1 are permitted, so make those intentional.
Afterward, export the comp and verify the generated tool's actual Center/Width/Height/SoftEdge plus EffectMask connections. Compare `color mask inspect` against the pre-chain for global canonicalization side effects and render/export a frame or matte view.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--center` (optional, default: `"0.5,0.5"`) — Center X,Y
- `--width` (optional, default: `0.5`) — Width
- `--height` (optional, default: `0.5`) — Height
- `--softness` (optional, default: `0.0`) — Soft edge
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- Width/height must be finite and strictly positive.
- SoftEdge is written only when softness > 0.
- Dry-run is unresolved: it validates geometry but does not check the clip/comp, predict the generated name, or reveal canonical rewiring.
- Connectivity validation does not prove rectangle geometry, softness, matte polarity/combine mode or rendered pixels.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color window rectangle --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
