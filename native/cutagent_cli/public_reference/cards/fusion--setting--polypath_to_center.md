# `fusion setting polypath-to-center`

Syntax: `cutagent fusion setting polypath-to-center X Y`

## Search terms

- PolyPath to Center
- Fusion coordinate conversion
- center-relative path coordinates
- normalized Center coordinates
- add 0.5 coordinates
- PolyPath X Y conversion
- mask point to Center
- Fusion path position conversion
- Polyline mask coordinates
- convert path point
- CenterX CenterY
- Fusion mask coordinate readback

## What it does

Convert PolyPath point coordinates to normalized Center coordinates.

## Do not use when

Do not use this command when the inputs are already normalized Center coordinates; adding 0.5 again produces the wrong result.
Do not use it to apply the result to a Fusion tool. It returns arithmetic only; a separate setting or graph mutation is required.
Do not assume output is clamped to 0..1. Any floats accepted by the CLI are converted.
Do not use global dry-run for a distinct plan. It performs the same addition and changes only metadata.

## Preflight and readback

Before execution, confirm the values are PolyPath’s center-relative X/Y coordinates and retain their sign and precision.
Round-trip critical results through `fusion setting center-to-polypath` and compare numerically with tolerance.
After applying the normalized coordinates to a real composition, inspect the resulting setting and export visual frames. Arithmetic success alone does not prove correct graph placement.
No cleanup is required because the command has no side effects.

## Public arguments and options

- `X` (required) — Fusion PolyPath X coordinate
- `Y` (required) — Fusion PolyPath Y coordinate

## Boundaries and gotchas

- X and Y are required positional floats.
- The command cannot identify whether a PolyPath point was originally authored in the wrong coordinate system.
- Visual verification is required only after a separate command applies the coordinates.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion setting polypath-to-center --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
