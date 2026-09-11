# `project db switch`

Syntax: `cutagent project db switch NAME [--type VALUE] [--force]`

## Search terms

- project db switch
- Switch project storage locations.
- project db switch help
- project db switch command

## What it does

Switch project storage locations.

## Do not use when

Do not use this for PostgreSQL or Cloud databases.
Do not switch while the current project has unsaved work. Save/export/archive first; switching may close it.
Do not assume the name alone is enough.

## Preflight and readback

Run dry-run while connected.

## Public arguments and options

- `NAME` (required) — Database name
- `--type` (optional, default: `"Disk"`) — Database type (currently only Disk)
- `--force/-f` (optional, default: `false`) — Actually switch databases when the target differs from the current database.

## Boundaries and gotchas

- Dry-run outputs only after proving the target exists.

## Stable public error codes

- `CONFIRMATION_REQUIRED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent project db switch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
