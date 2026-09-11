# `lut remove`

Syntax: `cutagent lut remove NAME`

## Search terms

- remove installed LUT
- delete user LUT
- LUT relative path
- dry-run LUT deletion
- remove LUT by basename
- safe LUT path containment
- LUT not found status
- cleanup installed cube
- refresh after LUT removal

## What it does

Remove a user-installed LUT.

## Do not use when

Do not use a bare basename when duplicates may exist in subfolders. The command removes only the first match and does not report ambiguity.
Do not use this on a file outside the user LUT root. Absolute and escaping names are rejected.
Do not use removal alone to prove DaVinci Resolve's cached LUT list changed. Run `lut-refresh` separately and verify the application state.
Do not expect empty parent directories to be removed; only the file is deleted.

## Preflight and readback

Re-run `lut list`, check the file no longer exists, and confirm unrelated same-named LUTs remain.
Refresh DaVinci Resolve's LUT list with a connected project and verify the removed LUT is no longer selectable.

## Public arguments and options

- `NAME` (required) — LUT file name or relative path

## Boundaries and gotchas

- Duplicate ambiguity is not detected or reported.
- Only candidates that currently exist and are files are removable.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent lut remove --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
