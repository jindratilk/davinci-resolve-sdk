# `lut-refresh`

Syntax: `cutagent lut-refresh`

## Search terms

- refresh LUT list
- reload DaVinci Resolve LUTs
- refresh installed cube
- current project LUT cache
- LUT refresh dry-run
- embedded bridge not running
- pending manual LUT verification

## What it does

Refresh the DaVinci Resolve LUT list.

## Do not use when

An operating-system process alone is insufficient.
Do not use it to install or remove files; use `lut install`/`lut remove` first.
Verification remains manual.
Do not expect `--resolve`, a path, folder, or LUT name option. The command refreshes the current project's whole LUT list.
Do not repeatedly refresh to work around an invalid LUT; validate the file, installation path, and actual DaVinci Resolve compatibility.

## Preflight and readback

Then inspect DaVinci Resolve's LUT UI, apply the exact LUT to a controlled clip/node, and compare a still or render. For removal, confirm the LUT is no longer selectable without disturbing existing grades.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Dry-run is treated as nonmutating.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent lut-refresh --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
