# `workflow plugin install`

Syntax: `cutagent workflow plugin install PATH [--user] [--all-users] [--overwrite]`

## Search terms

- install workflow plugin
- user workflow integration folder
- system workflow plugin
- all users plugin install

## What it does

Install a custom add-on.

## Do not use when

Do not use this before validating the plugin or when you need dependency registration, manifest migration, signing, or confirmation that DaVinci Resolve loaded it.

## Preflight and readback

Before execution, validate the source, choose user versus all-users scope, stop conflicting plugin activity, and use dry-run to inspect the exact destination. Afterward, verify copied contents and restart/reload DaVinci Resolve as required.

## Public arguments and options

- `PATH` (required) — Plugin folder path
- `--user` (optional, default: `false`) — Install into the user folder
- `--all-users` (optional, default: `false`) — Install into the system folder
- `--overwrite` (optional, default: `false`) — Replace an existing installed plugin

## Boundaries and gotchas

- Exact syntax is `cutagent workflow plugin install PATH [--user|--all-users] [--overwrite]`.
- Default scope and explicit `--user` are identical.
- Source existence is validated even in dry-run.
- Existing destination fails unless `--overwrite`.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent workflow plugin install --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
