# `color page power-window-overlay-transform`

Syntax: `cutagent color page power-window-overlay-transform [CLIP_NAME] [--shape VALUE] [--x VALUE] [--y VALUE] [--width VALUE] [--height VALUE] [--soft-1 VALUE] [--soft-2 VALUE] [--soft-3 VALUE] [--soft-4 VALUE] [--opacity VALUE] [--rotate VALUE] [--feather VALUE]`

## Search terms

- transform Power Window overlay
- move rectangle window
- resize Linear Power Window
- change window width and height
- adjust edge softness
- reposition box mask
- set rectangle opacity
- change overlay geometry numerically

## What it does

Set preset-backed Power Window overlay geometry by explicit values.

## Do not use when

Use `power-window-linear --node N` or `power-window-rectangle --node N` when targeting a specific Color node. Use shape-specific commands for Circle/Gradient/Polygon/Curve.

## Preflight and readback

Ensure at least one value is explicit.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--shape` (optional, default: `"linear"`)
- `--x` (optional)
- `--y` (optional)
- `--width` (optional)
- `--height` (optional)
- `--soft-1` (optional) — Linear/rectangle GUI Soft 1 value (0..62.5)
- `--soft-2` (optional) — Linear/rectangle GUI Soft 2 value (0..62.5)
- `--soft-3` (optional) — Linear/rectangle GUI Soft 3 value (0..62.5)
- `--soft-4` (optional) — Linear/rectangle GUI Soft 4 value (0..62.5)
- `--opacity` (optional) — Linear/rectangle GUI Opacity value (0..100)
- `--rotate` (optional)
- `--feather` (optional)

## Boundaries and gotchas

- At least one of x/y/width/height/Soft 1–4/opacity is required.
- `--rotate` and `--feather` always fail before mutation, even if other valid fields are present.
- Feathering must be expressed through the four explicit Soft values.
- This wrapper validates all supported values before dry-run, so its preview is stronger than the main Linear command: finite x/y -2..2, width/height .05..4, Soft 1–4 0..62.5, opacity 0..100.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page power-window-overlay-transform --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
