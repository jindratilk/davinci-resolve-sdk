# `color page power-window-linear`

Syntax: `cutagent color page power-window-linear [CLIP_NAME] [--node-index VALUE] [--x VALUE] [--y VALUE] [--width VALUE] [--height VALUE] [--soft-1 VALUE] [--soft-2 VALUE] [--soft-3 VALUE] [--soft-4 VALUE] [--opacity VALUE]`

## Search terms

- add Linear Power Window
- rectangular Color mask
- four-sided Power Window
- local rectangle grade
- move and resize linear window
- feather each window edge
- box vignette
- isolate rectangular area
- set Power Window opacity
- node-local linear mask

## What it does

Update a Color Page Linear Power Window using project readback.

## Do not use when

Use circle, gradient, polygon or curve commands for their actual shapes, and `power-window-track` for motion.

## Preflight and readback

Before mutation, inspect target node/container and existing windows, record geometry/softness, create a grade checkpoint and render reference. Inspect the Window overlay, add a visible local correction, and render inside/outside locality. Track separately when needed.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index; create/use an empty local node for secondaries
- `--x` (optional)
- `--y` (optional)
- `--width` (optional)
- `--height` (optional)
- `--soft-1` (optional) — Linear Power Window GUI Soft 1 value (0..62.5)
- `--soft-2` (optional) — Linear Power Window GUI Soft 2 value (0..62.5)
- `--soft-3` (optional) — Linear Power Window GUI Soft 3 value (0..62.5)
- `--soft-4` (optional) — Linear Power Window GUI Soft 4 value (0..62.5)
- `--opacity` (optional) — Linear Power Window GUI Opacity value (0..100)

## Boundaries and gotchas

- The command returns from dry-run before geometry validation.
- Preview does not establish range validity.
- Use GUI-set for rotation; do not fake it with x/y or unequal softness.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page power-window-linear --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
