# `lut convert`

Syntax: `cutagent lut convert PATH --format VALUE`

## Search terms

- convert LUT format
- cube LUT passthrough
- validate cube conversion
- unsupported 3dl LUT
- LUT conversion not available
- local LUT format check
- cube extension validation
- LUT convert dry-run read

## What it does

Check LUT format support.

## Do not use when

Do not use this expecting a converted output file. There is no output option and `converted` is always false.
Do not interpret `valid:true` as complete LUT correctness. The validator does not parse size, domains, RGB row structure/count, numeric bounds, NaN/Inf, or application compatibility.
Check `status`, `feature`, and `reason`.
Do not use an unsupported-format result to prove the source exists or is readable; that branch returns before source validation.
Do not assume global dry-run avoids file access.
Do not use this as DaVinci Resolve installation/refresh/apply verification; use install/list/validate plus DaVinci Resolve refresh and real application/render evidence.

## Preflight and readback

For cube passthrough, run `lut validate` and `lut inspect`, then independently parse/check row count and numeric structure. Treat this command as a support gate, not conversion.

## Public arguments and options

- `PATH` (required) — Source LUT path
- `--format` (required) — Target format, currently cube

## Boundaries and gotchas

- Required option is `--format TEXT`.
- Only exact lowercased `cube` enters source validation.
- There is no dedicated dry-run handling.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent lut convert --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
