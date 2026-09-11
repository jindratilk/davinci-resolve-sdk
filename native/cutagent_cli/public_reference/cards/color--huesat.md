# `color huesat`

Syntax: `cutagent color huesat [--hue-shift VALUE] [--sat-boost VALUE] [--val-boost VALUE] [--output VALUE]`

## Search terms

- generate hue rotation LUT
- make saturation boost cube
- create HSV brightness LUT
- shift all colors by degrees
- desaturate with 3D LUT
- bake hue sat value transform
- create 33 point HueSat LUT

## What it does

Generate LUT from hue and saturation modifications.

## Do not use when

Use `color lut --set` only after file inspection if this generated LUT should affect a node. Do not use a global HSV transform for skin-protected, hue-selective, gamut-aware, HDR, spatial, or color-managed corrections.

## Preflight and readback

Dry-run to validate finite inputs and parent path, and preserve any existing destination. Test the LUT in the destination project’s color-management context before installing it. If applying with `color lut`, render a representative frame and separately clean the library copy when no longer needed.

## Public arguments and options

- `--hue-shift` (optional, default: `0.0`) — Hue rotation in degrees
- `--sat-boost` (optional, default: `1.0`) — Saturation multiplier
- `--val-boost` (optional, default: `1.0`) — Value/brightness multiplier
- `--output/-o` (optional) — Output .cube file

## Boundaries and gotchas

- Multipliers have no nonnegative or upper bounds; only finiteness is validated.
- The HSV operation is performed on numeric RGB lattice values with no knowledge of input transfer function, gamut, HDR range, data levels, or project color management.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color huesat --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
