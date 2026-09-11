# `embedded install`

Syntax: `cutagent embedded install [--sandbox]`

## Search terms

- install CutAgent Lua script
- enable CutAgent in DaVinci Resolve Free
- set up embedded bridge
- add CutAgent to Workspace Scripts
- reinstall outdated embedded bridge
- install App Store DaVinci Resolve support
- repair embedded protocol mismatch

## What it does

Install CutAgent support in DaVinci Resolve.

## Do not use when

Use `embedded ping` when both sides appear connected and a round-trip health check is needed. Use `embedded uninstall --force` only when intentionally removing support.
Do not pass `--sandbox` for the normal Blackmagic Design website installation of DaVinci Resolve on macOS; that creates a second copy under the App Store container, which the normal application does not read.

## Preflight and readback

Before installation, run `embedded status` or `embedded install --dry-run`. Choose standard versus App Store sandbox from the actual installed DaVinci Resolve edition.
Confirm matching bridge/protocol versions, valid auth and `connected:true`, then use `embedded ping`. On Windows also require the socket asset to be installed and current.

## Public arguments and options

- `--sandbox` (optional, default: `false`) — Install into the App Store sandbox container path

## Boundaries and gotchas

- Installing does not create a valid broker auth file; server lifecycle owns that.
- On macOS the response still describes the asset but correctly reports `applicable:false` and does not install it.
- The command does not inspect which DaVinci Resolve edition is installed.

## Examples

- `cutagent embedded install --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
