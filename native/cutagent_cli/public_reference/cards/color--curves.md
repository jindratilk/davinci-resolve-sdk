# `color curves`

Syntax: `cutagent color curves [--red VALUE] [--green VALUE] [--blue VALUE] [--master VALUE] [--output VALUE]`

## Search terms

- generate curve LUT
- bake RGB curves into cube
- create S curve LUT file
- adjust red green blue response curve
- make 33 point 3D LUT
- create master contrast curve LUT
- export separable channel curves

## What it does

Generate LUT from RGB curves.

## Do not use when

Use `lut install` followed by `color lut` if the generated file must become available and be applied. This generator is separable per channel; do not use it for hue-dependent changes, gamut mapping, cross-channel matrices, spatial masks, qualifiers, or temporal effects.

## Preflight and readback

Afterward, verify the header, exact 33-point size and 35,937 data rows, sample known lattice coordinates, and test the LUT on controlled imagery in the project’s color-management context. Install/apply it explicitly only after that file-level inspection.

## Public arguments and options

- `--red` (optional) — Red curve points '0,0;0.5,0.6;1,1'
- `--green` (optional) — Green curve points
- `--blue` (optional) — Blue curve points
- `--master` (optional) — Master curve points
- `--output/-o` (optional) — Output .cube file

## Boundaries and gotchas

- Duplicate x positions are accepted and can produce discontinuous/ambiguous interpolation depending on the adjacent sorted segment.
- Every point must be finite and each coordinate must be within 0–1.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color curves --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
