# `storage files`

Syntax: `cutagent storage files PATH`

## Search terms

- list Media Storage files
- DaVinci Resolve MediaStorage
- list folders before files
- storage path validation
- media browser inventory

## What it does

List files in a storage location.

## Do not use when

Do not use the listing as proof that media is readable, importable, online, or supported.

## Preflight and readback

Preserve `source` for each item and expect paths/usernames to require redaction when sharing output.
After selecting media, validate the exact path and file type before import.

## Public arguments and options

- `PATH` (required) — Path to browse

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent storage files --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
