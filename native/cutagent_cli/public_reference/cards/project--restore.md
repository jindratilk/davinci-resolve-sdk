# `project restore`

Syntax: `cutagent project restore PATH`

## Search terms

- restore DaVinci Resolve project archive
- restore DRA archive
- archived project recovery
- unsafe dry-run restore
- project archive path
- Project Manager restore
- archive disaster recovery
- restored project verification

## What it does

Restore a project from archive.

## Do not use when

Do not run global `--dry-run` as a preview; it does not prevent restoration.

## Public arguments and options

- `PATH` (required) — Path to archived project file

## Boundaries and gotchas

- There are no local options; `--name` is invalid.
- This is a dangerous dry-run contract violation.
- There is no confirmation or `--force` gate.
- A false result is the only explicit failure condition.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent project restore --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
