# `script uninstall`

Syntax: `cutagent script uninstall NAME --page VALUE [--all-users]`

## Search terms

- uninstall DaVinci Resolve script
- remove Fusion Scripts file
- delete Utility script
- user versus all-users script
- safe script relative path
- DaVinci Resolve page folder
- script removal dry-run
- installed script not found
- remove Python Lua menu script

## What it does

Uninstall a DaVinci Resolve custom edit.

## Do not use when

Do not remove a script without confirming exact scope, page, relative path, ownership, and whether another workflow depends on it.
Do not expect this to stop a currently running script or unload code already loaded by DaVinci Resolve.
Do not use a basename when duplicate/nested scripts exist; pass the exact page-relative path from `script list`.

## Preflight and readback

Run dry-run and verify its resolved absolute path.
For system entries, add `--all-users` deliberately and ensure appropriate permissions are available.

## Public arguments and options

- `NAME` (required) — Installed script file name
- `--page` (required) — Utility|Edit|Color|Deliver|Fusion
- `--all-users` (optional, default: `false`) — Remove from the system support folder

## Boundaries and gotchas

- Exact help is `cutagent script uninstall NAME --page PAGE [--all-users]`.
- `--page` is required.
- Page text is stripped but remains case-sensitive.
- The command does not connect to DaVinci Resolve.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent script uninstall --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
