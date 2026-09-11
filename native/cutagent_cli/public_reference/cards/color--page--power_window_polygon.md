# `color page power-window-polygon`

Syntax: `cutagent color page power-window-polygon [CLIP_NAME] [--node-index VALUE] [--points VALUE]`

## Search terms

- draw Polygon Power Window
- straight-sided custom mask
- multi-point Color mask
- isolate object with polygon
- custom angular window
- closed polygon matte
- garbage matte polygon
- node-local polygon selection
- trace building with Power Window
- create five-point mask

## What it does

Update a Color Page Polygon Power Window using project readback.

## Do not use when

Use `power-window-track` after the static polygon is correct.

## Preflight and readback

Before mutation, verify timeline resolution/aspect, target Color node and existing window type; create an empty serial node for an isolated secondary and save a grade/matte/render checkpoint. Order perimeter vertices consistently and inspect for self-intersection. Track separately if the subject moves.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index; create/use an empty local node for secondaries
- `--points` (optional) — Polygon Power Window points as normalized 'x,y;x,y;x,y' pairs

## Boundaries and gotchas

- The polygon is implicitly closed; do not needlessly repeat the first point.
- Repeating/duplicating points, self-intersection, zero area and winding are not validated, only minimum count, finiteness and 0..1 bounds.
- This still does not prove the visible matte or rendered locality.
- The clip must already have an active grade/version body in a local Disk project.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page power-window-polygon --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
