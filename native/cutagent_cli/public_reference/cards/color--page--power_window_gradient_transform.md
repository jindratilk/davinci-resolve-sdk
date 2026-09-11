# `color page power-window-gradient-transform`

Syntax: `cutagent color page power-window-gradient-transform [CLIP_NAME] [--angle VALUE] [--softness VALUE] [--x VALUE] [--y VALUE]`

## Search terms

- move Gradient Power Window
- reposition gradient mask
- change gradient softness
- pan Gradient window
- tilt Gradient window
- center graduated filter
- adjust Gradient Soft 1
- transform gradient matte
- shift sky gradient

## What it does

Runs the public `color page power-window-gradient-transform` CutAgent command.

## Do not use when

Use `power-window-linear` or overlay-transform for linear/rectangle geometry.

## Preflight and readback

Save a grade checkpoint and matte/render reference. Supply finite GUI values deliberately—normally 50 is centered—and convert desired softness mentally to the effective accepted GUI range. After reopen, inspect returned shape/pan/tilt/gradient size, confirm the same project/timeline/clip, view the overlay, and render a visible local correction to prove placement/locality.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--angle` (optional)
- `--softness` (optional) — Gradient Soft 1 GUI value
- `--x` (optional) — Gradient Pan GUI value; 50.0 is centered
- `--y` (optional) — Gradient Tilt GUI value; 50.0 is centered

## Boundaries and gotchas

- There is no `--node`; this cannot reliably transform a Gradient living only in node 2+.
- `--angle` is deliberately rejected.
- Dry-run returns before softness conversion/validation.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page power-window-gradient-transform --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
