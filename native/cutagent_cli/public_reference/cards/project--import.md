# `project import`

Syntax: `cutagent project import PATH`

## Search terms

- import DaVinci Resolve project
- import DRP file
- project file ingestion
- unsafe dry-run import
- project name collision
- imported project verification
- DRP compatibility

## What it does

Import a project from file.

## Do not use when

Do not run global `--dry-run` assuming it prevents mutation; it does not for this command.

## Public arguments and options

- `PATH` (required) — Path to .drp file

## Boundaries and gotchas

- There are no local options; `--name` is invalid.
- This is a dangerous dry-run contract violation; use no command invocation as preview when connected.
- No confirmation or `--force` gate exists.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project import --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
