# `color page warper-set`

Syntax: `cutagent color page warper-set [CLIP_NAME] [--point VALUE] [--to VALUE]`

## Search terms

- move one Color Warper pin
- warp one chroma region
- drag a color on the Color Warper map
- pull one color toward another
- remap a hue/chroma point
- single-pin Chroma Warp
- shift a sampled color in Color Warper
- change one color family with a pin
- source and target Color Warper coordinates
- localized chroma remap without qualifier
- Color page Pin Point tool

## What it does

Runs the public `color page warper-set` CutAgent command.

## Do not use when

Use `color page hue-curve-set`/`hue-curve-spline-set` when the correction should be expressed as a hue-indexed curve rather than a spatial point on the Chroma Warp map. Use `color page sat-curve-set` or `primary-set --sat` for saturation shaping without moving a chroma point. Do not use this command for Color Warper Hue-Saturation mode, Chroma-Luma mode, mesh-index edits, freehand strokes, multiple pins, adjustable falloff/radius or a full grid deformation: none of those controls are exposed by the CLI surface. Use the DaVinci Resolve UI for those unsupported Warper operations rather than inventing flags from the obsolete generated example.

## Preflight and readback

Save/export the grade because this route replaces the single-pin key and can coexist unpredictably with preserved mesh/stroke parameters. Confirm node 1 is the intended creative node, identify source and target coordinates from the actual Chroma Warp map, and dry-run both pairs.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--point` (optional) — Source Color Warper map coordinate as normalized x,y
- `--to` (optional) — Target Color Warper map coordinate as normalized x,y

## Boundaries and gotchas

- Both `--point` and `--to` are required and each must contain exactly two comma-separated finite floats.
- It replaces the existing parameter at the legacy single-pin key; it cannot append a second pin or preserve an existing pin collection.
- The only command-level automated test covers dry-run argument mapping.
- The active command does not accept `--mode`, `--mesh-index`, `--delta-x`, `--delta-y`, or `--require-render-proof`; those flags appear only in the obsolete generated command-index example and are invalid CLI syntax.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page warper-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
