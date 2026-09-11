# `lut inspect`

Syntax: `cutagent lut inspect PATH`

## Search terms

- inspect LUT file
- count cube entries
- cube LUT diagnostics
- malformed LUT rows
- validate LUT suffix
- local LUT read
- LUT entry counter
- dry-run LUT inspection

## What it does

Inspect a LUT file.

## Do not use when

Do not use this as proof that a LUT is syntactically correct, numerically valid, complete, or accepted by DaVinci Resolve.
Do not compare `entries` with `size³` unless you independently parse the size and rows. This command neither performs nor reports that comparison.
Do not trust `entries` for negative-number or leading-decimal rows.
Do not assume `valid:false` is a command failure.
Do not assume global dry-run avoids file access.
Do not use it to install, refresh, apply, or visually verify a LUT in DaVinci Resolve.

## Preflight and readback

Preserve the file if another process may modify it.
Run inspection, then independently parse the header and every data row. Require exactly three finite numeric values per row and the expected `size³` count; enforce any required range/domain rules.
After inspection, distinguish command success from LUT validity.
For DaVinci Resolve use, separately install into a scoped location, refresh the LUT list, apply the intended LUT, and verify the visual/render result.

## Public arguments and options

- `PATH` (required) — .cube path

## Boundaries and gotchas

- Suffix comparison is case-insensitive.
- The size token is not parsed or range-checked.
- The counter does not validate token count, numeric parsing, finite values, ranges, ordering, or declared cube size.

## Stable public error codes

- `INVALID_OPTION`
- `VALIDATION_ERROR`

## Examples

- `cutagent lut inspect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
