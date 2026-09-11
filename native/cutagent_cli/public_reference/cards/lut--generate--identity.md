# `lut generate identity`

Syntax: `cutagent lut generate identity --size VALUE --output VALUE [--overwrite]`

## Search terms

- generate identity LUT
- create cube LUT
- 3D LUT size
- identity RGB cube
- overwrite LUT output
- Curves LUT title
- validate generated cube
- LUT size cubed entries

## What it does

Generate an identity.cube LUT.

## Do not use when

Do not use an unbounded large size without estimating `size³` rows, memory/time, and disk cost. There is no maximum.
Do not assume generated identity content is installed or visible in DaVinci Resolve. Installation, refresh, list, application, and render verification are separate.

## Preflight and readback

Preserve any existing file before authorizing overwrite.
Remember parent/suffix validation is incomplete.
For product LUTs, install into a scoped folder, refresh DaVinci Resolve LUTs, and verify an actual application/render.

## Public arguments and options

- `--size` (required) — Cube size
- `--output` (required) — Output .cube path
- `--overwrite` (optional, default: `false`) — Replace an existing output file

## Boundaries and gotchas

- Required options are `--size INTEGER` and `--output TEXT`.
- `--overwrite` replaces an existing output.
- Dry-run checks size and path conflict only.
- Success returns path, requested size, and `generated:true` only.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent lut generate identity --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
