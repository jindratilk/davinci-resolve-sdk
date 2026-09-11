# `color page power-window-circle-detail`

Syntax: `cutagent color page power-window-circle-detail [CLIP_NAME] [--opacity VALUE] [--soft-2 VALUE] [--soft-3 VALUE] [--soft-4 VALUE] [--invert]`

## Search terms

- change Circle window opacity
- invert circular Power Window
- restore inside Circle selection
- adjust Circle mask strength
- Circle window detail controls
- turn Circle mask outside
- lower circular matte opacity
- toggle Circle inversion

## What it does

Runs the public `color page power-window-circle-detail` CutAgent command.

## Do not use when

Use `power-window-circle` when targeting a specific Color node, preserving/choosing a nondefault size explicitly, or setting Soft 1/pan/tilt. Use shape-specific commands for non-Circle windows, and `power-window-track` for motion.

## Preflight and readback

If its size is not exactly 288, prefer the main Circle command and pass that size explicitly. Save a grade checkpoint and rendered/matte reference. If the command created a Circle unexpectedly, remove it or restore the checkpoint rather than assuming it only changed metadata.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--opacity` (optional) — Circle Power Window GUI Opacity value, 0..100
- `--soft-2` (optional)
- `--soft-3` (optional)
- `--soft-4` (optional)
- `--invert/--no-invert` (optional) — Set the outside/inverted Circle Power Window selection

## Boundaries and gotchas

- Therefore changing only opacity or invert also forces size 288.
- There is no `--node`.
- It cannot safely target a Circle on a later node.
- At least one of opacity or invert/no-invert is required; calling with only a clip is rejected.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page power-window-circle-detail --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
