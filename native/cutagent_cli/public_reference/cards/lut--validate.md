# `lut validate`

Syntax: `cutagent lut validate PATH`

## Search terms

- validate LUT file
- cube extension check
- shallow LUT validation
- malformed cube accepted
- LUT validity flag
- local LUT check
- wrong LUT suffix
- dry-run LUT read

## What it does

Validate a LUT file.

## Do not use when

Do not use `valid:true` as proof that the LUT can be parsed, has the declared number of rows, contains valid RGB triplets, or works in DaVinci Resolve.
Do not use this when you need entry diagnostics; `lut inspect` adds the approximate `entries` field, though that counter is also heuristic.
Suffix is part of the test.
Do not assume global dry-run avoids reading the source.
Do not use validation as installation, refresh, application, or render verification.

## Preflight and readback

Independently parse the returned size token, check its allowed range, parse every RGB triplet as finite numbers, and compare the exact row count with `size³`.
Before production use, install and refresh through the intended LUT workflow, apply the LUT in DaVinci Resolve, and verify the image or render independently.

## Public arguments and options

- `PATH` (required) — .cube path

## Boundaries and gotchas

- No numeric range, finite-value, triplet-count, ordering, domain, title, or cube-size consistency checks occur.
- Global dry-run has no special branch.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent lut validate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
