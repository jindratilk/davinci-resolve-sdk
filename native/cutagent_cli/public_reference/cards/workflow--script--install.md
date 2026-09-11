# `workflow script install`

Syntax: `cutagent workflow script install PATH [--name VALUE] [--overwrite]`

## Search terms

- install workflow script
- Utility scripts folder
- copy workflow callback
- Fusion Scripts Utility

## What it does

Install a custom DaVinci Resolve edit.

## Do not use when

Do not use this to execute, register as a Workflow Integration callback, validate, or install for all users; this wrapper always targets the user's Utility scripts folder.

## Preflight and readback

Before execution, syntax-check and review the source, choose a safe installed filename, and dry-run the destination. Afterward, confirm the copied file, restart/refresh DaVinci Resolve as required, and test from Workspace > Scripts > Utility.

## Public arguments and options

- `PATH` (required) — Script path
- `--name` (optional) — Installed file name
- `--overwrite` (optional, default: `false`) — Replace an existing installed script

## Boundaries and gotchas

- Exact syntax is `cutagent workflow script install PATH [--name NAME] [--overwrite]`.
- Source must exist even in dry-run.
- Dry-run checks source/conflict and performs no copy.

## Examples

- `cutagent workflow script install --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
