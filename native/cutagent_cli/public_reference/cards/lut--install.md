# `lut install`

Syntax: `cutagent lut install PATH [--folder VALUE] [--overwrite]`

## Search terms

- install LUT
- user DaVinci Resolve LUT folder
- copy cube LUT
- LUT subfolder
- overwrite installed LUT
- dry-run LUT install
- safe LUT relative folder
- install DCTL file
- refresh LUT after install

## What it does

Install a LUT into the user DaVinci Resolve LUT folder.

## Do not use when

Do not use this as LUT validation. The command accepts arbitrary file suffixes/content and can also copy whole directories.
Do not use an absolute or escaping `--folder`; only a path resolving beneath the user LUT root is allowed.
Do not expect installation to refresh DaVinci Resolve's LUT cache. Run `lut-refresh` separately and verify availability/application.

## Preflight and readback

Back up any destination before permitting overwrite.
For temporary verification, remove the exact relative path with `lut remove`, confirm it disappears from the list, and clean only the now-empty test folder.

## Public arguments and options

- `PATH` (required) — LUT path
- `--folder` (optional) — User LUT subfolder
- `--overwrite` (optional, default: `false`) — Replace an existing installed LUT

## Boundaries and gotchas

- `--folder TEXT` is optional and relative to the user LUT root.
- `--overwrite` is required to replace an existing destination.
- `--folder` is expanded/resolved and must remain beneath that root.
- It also does not verify that DaVinci Resolve discovered or can apply the LUT.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent lut install --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
