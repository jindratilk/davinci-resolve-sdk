# `layout import`

Syntax: `cutagent layout import PATH [NAME]`

## Search terms

- import DaVinci Resolve layout preset
- import drfx UI preset
- named layout import
- layout preset filename
- embedded layout import unsupported
- invalid layout preset file
- layout recovery round trip

## What it does

Import a layout preset from file.

## Do not use when

Do not import an untrusted or unverified file into a production workspace.
Independently inspect the Workspace menu and load the imported preset safely.

## Preflight and readback

Inspect Workspace > Layout Presets and choose a unique explicit name when deterministic naming matters. Because no public scripting list method exists, this collision check must be independent.
Run global dry-run and confirm the expanded path and normalized optional name. Remember that dry-run validates no file signature or DaVinci Resolve compatibility.
For temporary verification, delete only the uniquely imported name after the load test and confirm it is absent while unrelated presets remain. Keep the source export until the round trip and cleanup both succeed.

## Public arguments and options

- `PATH` (required) — Layout preset file path
- `NAME` (optional) — Preset name (optional)

## Boundaries and gotchas

- When no name is supplied, dry-run target name is JSON null.
- Success does not report file size, checksum, parsed preset identity, captured panel state, collision status, or import/load round-trip result.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent layout import --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
