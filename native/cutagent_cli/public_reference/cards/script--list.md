# `script list`

Syntax: `cutagent script list`

## Search terms

- list installed DaVinci Resolve scripts
- Fusion Scripts inventory
- user and all-users scripts
- Utility Edit Color Deliver Fusion
- Python Lua script discovery
- recursive script folder scan
- installed script relative path
- DaVinci Resolve menu scripts
- audit scripting support folders

## What it does

List DaVinci Resolve custom edits.

## Do not use when

Do not treat this as a list of scripts currently loaded, enabled, trusted, syntactically valid, or visible in the DaVinci Resolve UI.
Do not use a basename alone to identify a nested or duplicated script; preserve scope, page, and relative path.
Do not expect it to scan arbitrary custom script directories or environment-configured search paths.
Do not publish the raw output without reviewing absolute user/system paths.

## Preflight and readback

After installing or uninstalling, rerun the command and compare the relevant exact row. Separately refresh/restart DaVinci Resolve and verify actual menu visibility and script execution.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- It scans user scope first, then all-users scope.
- The command does not inspect file contents, shebangs, syntax, permissions, ownership, signatures, or hashes.
- It does not distinguish first-party, third-party, bundled, generated, or malicious scripts.
- It does not identify duplicate contents.
- `name` is only the basename and may collide across pages/scopes/nested folders.
- Empty results do not prove DaVinci Resolve has no runnable scripts outside these known roots.

## Examples

- `cutagent script list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
