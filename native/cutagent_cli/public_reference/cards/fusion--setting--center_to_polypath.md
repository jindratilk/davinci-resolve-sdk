# `fusion setting center-to-polypath`

Syntax: `cutagent fusion setting center-to-polypath X Y`

## Search terms

- Center to PolyPath
- Fusion coordinate conversion
- normalized Center coordinates
- PolyPath point coordinates
- subtract 0.5 coordinates
- Center X Y conversion
- mask path coordinate system
- Fusion 0..1 coordinates
- center-relative path points
- Polyline path placement
- convert normalized position
- PolyPath X Y

## What it does

Convert normalized Center coordinates to PolyPath point coordinates.

## Do not use when

Do not use this command to mutate a PolyPath or Fusion input. Apply the returned coordinates with the appropriate graph or setting authoring command.
Do not use it when the source values are already center-relative PolyPath coordinates; that would subtract 0.5 twice.
Do not assume inputs are constrained to 0..1.
Do not use global dry-run for different behavior.

## Preflight and readback

Before execution, identify whether the source coordinate is a normalized Center value or a center-relative PolyPath point. Confirm X/Y order and retain enough decimal precision.
After execution, use the `polypath` object, not the echoed `center` object.
Independently round-trip important coordinates through `fusion setting polypath-to-center` before writing a production mask or path.
No cleanup is required because no file or project state changes.

## Public arguments and options

- `X` (required) — Normalized Fusion Center X, usually 0..1
- `Y` (required) — Normalized Fusion Center Y, usually 0..1

## Boundaries and gotchas

- Both X and Y are required positional floats.
- No finite-range or 0..1 validation is implemented.
- `fusion setting inspect` may warn when all PolyPath points lie in 0..1, but this converter does not emit that warning itself.
- Pixel or graph verification is still required after using the value in a real composition.

## Stable public error codes

- `INVALID_OPTION`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion setting center-to-polypath --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
