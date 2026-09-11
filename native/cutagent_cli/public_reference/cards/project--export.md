# `project export`

Syntax: `cutagent project export NAME PATH [--with-stills]`

## Search terms

- export DaVinci Resolve project
- create DRP file
- export project stills
- no-stills project export
- verify DRP artifact
- current folder project export
- project export path

## What it does

Export a project to file.

## Preflight and readback

Run connected dry-run and review normalized path, stills flag, project existence, and current-project match.
Keep the source project unchanged until the import smoke succeeds.

## Public arguments and options

- `NAME` (required) — Project name
- `PATH` (required) — Export path
- `--with-stills/--no-stills` (optional, default: `true`)

## Boundaries and gotchas

- Exact syntax is `cutagent project export NAME PATH [--with-stills|--no-stills]`.
- Only the parent must exist; target collision is not checked.
- Name comparisons are case-sensitive.
- There is no `--force` or confirmation prompt.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent project export --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
