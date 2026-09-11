# `color page power-window-rectangle`

Syntax: `cutagent color page power-window-rectangle [CLIP_NAME] [--node-index VALUE] [--x VALUE] [--y VALUE] [--width VALUE] [--height VALUE] [--soft-1 VALUE] [--soft-2 VALUE] [--soft-3 VALUE] [--soft-4 VALUE] [--opacity VALUE] [--require-render-proof]`

## Search terms

- add rectangular Power Window
- rectangle mask
- box-shaped local grade
- crop-like Color mask
- feather rectangle edges
- move rectangle window
- resize box vignette
- isolate screen or sign
- rectangular secondary correction
- verify rectangle changes render

## What it does

Update DaVinci Resolve rectangular Linear Power Window using project readback.

## Do not use when

Use Circle/Gradient/Polygon/Curve for different shapes and `power-window-track` for motion. Do not enable render proof on a newly created window in an otherwise neutral node unless a visible node-local correction already exists; the mask alone may not change pixels.

## Preflight and readback

Before mutation, inspect the target node, existing Linear window and local correction; save a grade checkpoint and reference frame. If requesting render proof, ensure the targeted node produces a visible effect whose localization/geometry should change the image. Inspect the overlay and rendered locality.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index; create/use an empty local node for secondaries
- `--x` (optional)
- `--y` (optional)
- `--width` (optional)
- `--height` (optional)
- `--soft-1` (optional) — Rectangle/Linear Power Window GUI Soft 1 value (0..62.5)
- `--soft-2` (optional) — Rectangle/Linear Power Window GUI Soft 2 value (0..62.5)
- `--soft-3` (optional) — Rectangle/Linear Power Window GUI Soft 3 value (0..62.5)
- `--soft-4` (optional) — Rectangle/Linear Power Window GUI Soft 4 value (0..62.5)
- `--opacity` (optional) — Rectangle/Linear Power Window GUI Opacity value (0..100)
- `--require-render-proof` (optional, default: `false`) — Export before/after Color Page frames and fail unless the rendered image changes

## Boundaries and gotchas

- Rectangle is an agent/user-facing alias only.
- Dry-run exits before geometry validation and does not disclose `--require-render-proof`.
- `--require-render-proof` tests final pixels, not window presence.
- An empty/neutral node with only a mask should produce identical frames and fail; a pre-existing correction localized by the rectangle should change.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page power-window-rectangle --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
