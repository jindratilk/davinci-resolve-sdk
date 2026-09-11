# `workflow plugin uninstall`

Syntax: `cutagent workflow plugin uninstall PLUGIN_ID [--user] [--all-users]`

## Search terms

- uninstall workflow plugin
- delete workflow integration
- user plugin removal
- all users plugin removal

## What it does

Remove a custom add-on.

## Do not use when

Do not use this with an unverified id/path, when files must be preserved, or as a disable/toggle mechanism; an existing target is permanently deleted.

## Preflight and readback

Afterward, confirm removal and restart/reload DaVinci Resolve if needed.

## Public arguments and options

- `PLUGIN_ID` (required) — Plugin folder/ID
- `--user` (optional, default: `false`) — Remove from the user folder
- `--all-users` (optional, default: `false`) — Remove from the system folder

## Boundaries and gotchas

- Default scope and `--user` both mean user support.
- `--user` plus `--all-users` is rejected.

## Examples

- `cutagent workflow plugin uninstall --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
