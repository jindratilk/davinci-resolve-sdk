# `project db backup`

Syntax: `cutagent project db backup NAME PATH`

## Search terms

- project db backup
- Back up the project.
- project db backup help
- project db backup command

## What it does

Back up the project.

## Do not use when

Do not use an absent, ambiguous, non-Disk, or rootless source.

## Preflight and readback

Before execution, identify the exact library name, choose a unique destination with enough free space, coordinate writes, and run dry-run.
Restore-test production backups under a separate name/location.

## Public arguments and options

- `NAME` (required) — Database name
- `PATH` (required) — Backup output path

## Boundaries and gotchas

- The destination must not exist and is never overwritten.

## Examples

- `cutagent project db backup --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
