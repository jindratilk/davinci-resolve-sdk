# `color window ellipse`

Syntax: `cutagent color window ellipse [--clip VALUE] [--center VALUE] [--width VALUE] [--height VALUE] [--softness VALUE] [--comp VALUE]`

## Search terms

- add elliptical grading window
- create oval Fusion mask
- isolate face with ellipse
- vignette mask for color correction
- add circular color window
- make soft ellipse mask
- spotlight subject with oval window
- create offscreen ellipse matte
- mask ColorCorrector with ellipse
- add Fusion EllipseMask to clip
- create feathered oval grading region
- add round power-window-like mask

## What it does

Add an elliptical grading window using Fusion mask.

## Do not use when

Use `color window rectangle` for a box, `window polygon` for an arbitrary outline, `window attach` for an existing orphaned mask, and `window reorder` when no new tool is needed. Use `tracker attach-window` when a specific mask must feed a specific tracker rather than joining the global canonical stack.
Modify the existing Fusion tool through a tool/input command or detach/delete/recreate deliberately.

## Preflight and readback

Before creation, inspect/export the target Fusion comp, list current windows and orphaned helpers, confirm the exact timeline item/comp, and choose normalized geometry. Treat 0.5,0.5 as frame center; decide deliberately whether center or dimensions outside 0–1 are desired.
Check the expanded chain for reactivated orphaned tools or displaced custom main-chain effects. Render/export a frame or mask view to verify geometry, feathering and combine behavior. Save only after visual approval.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--center` (optional, default: `"0.5,0.5"`) — Center X,Y
- `--width` (optional, default: `0.5`) — Width
- `--height` (optional, default: `0.5`) — Height
- `--softness` (optional, default: `0.0`) — Soft edge
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- Width and height must be finite and strictly greater than zero.
- Softness must be finite/non-negative; center must be exactly two comma-separated finite numbers.
- Their actual combined matte depends on Fusion mask defaults/settings and must be viewed/rendered.
- Dry-run is unresolved and creates nothing.
- It validates/normalizes geometry but does not prove clip/comp availability or predict the generated name/global rewiring.
- Graph validation proves connectivity only, not geometry, softness, matte polarity, combine mode or rendered pixels.

## Examples

- `cutagent color window ellipse --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
