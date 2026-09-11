# `color page power-window-circle`

Syntax: `cutagent color page power-window-circle [CLIP_NAME] [--node-index VALUE] [--size VALUE] [--soft-1 VALUE] [--pan VALUE] [--tilt VALUE] [--opacity VALUE] [--invert]`

## Search terms

- add circular Power Window
- oval mask
- vignette window
- spotlight a face
- isolate round area
- circle mask on Color node
- soften circular mask
- move Power Window center
- invert circle selection
- local grade inside ellipse

## What it does

Update a Color Page Circle Power Window using project readback.

## Do not use when

Use `power-window-circle-detail` only for the first/root Circle's opacity/invert controls, understanding that it also rewrites size to 288. Use rectangle, linear, gradient, polygon or curve commands for those shapes; a Circle command refuses to replace a different window on an explicitly targeted node. Use `power-window-track` after creating the window when it must follow motion, and a node-local primary/wheel command to define what the matte actually affects. For a conventional edge vignette based on fixed geometry, Circle is appropriate; for semantic subject selection use Magic Mask.

## Preflight and readback

Before mutation, inspect the Color graph and current Power Windows, create an empty serial node for a secondary if the target node already contains non-window parameters, record the current circle values, and save/render a reference. Run tracking separately when needed.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index; create/use an empty local node for secondaries
- `--size` (optional, default: `288.0`) — Circle Power Window size in DaVinci Resolve DB units
- `--soft-1` (optional) — Circle Power Window GUI Soft 1 value, 0..100
- `--pan` (optional) — Circle Power Window GUI Pan value, 0..100 with 50 centered
- `--tilt` (optional) — Circle Power Window GUI Tilt value, 0..100 with 50 centered
- `--opacity` (optional) — Circle Power Window GUI Opacity value, 0..100
- `--invert/--no-invert` (optional) — Set the outside/inverted Circle Power Window selection

## Boundaries and gotchas

- Re-running without `--size` always writes 288 and can resize an existing Circle.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page power-window-circle --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
