# `embedded uninstall`

Syntax: `cutagent embedded uninstall [--sandbox] [--force]`

## Search terms

- uninstall CutAgent Lua script
- remove embedded bridge support
- delete CutAgent from Workspace Scripts
- remove DaVinci Resolve Free integration
- uninstall App Store sandbox script
- remove stale CutAgent.lua
- clean up legacy CutAgent scriptlib

## What it does

Remove CutAgent support from DaVinci Resolve.

## Do not use when

If the goal is only to stop the current broker, terminate its supervised `embedded start-server` process; uninstalling files is not server lifecycle control.
Do not remove the standard copy when only the App Store installation should be cleaned, or vice versa. Do not use this command as a temporary disconnect mechanism: a script already loaded in memory and the broker/auth file are separate.

## Preflight and readback

Before deletion, run `embedded status`, identify the exact standard/sandbox row used by the installed DaVinci Resolve edition, and preserve any customized script separately. Stop or account for running clients if a clean shutdown matters.
Confirm the other installation variant remains intact. If removing active support, stop the broker and remove/let it clean its auth file separately; verify Workspace > Scripts no longer exposes the item after DaVinci Resolve refresh/restart.

## Public arguments and options

- `--sandbox` (optional, default: `false`) — Remove from the App Store sandbox container path
- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- Global `--dry-run` does not protect this command.
- `--sandbox` is not an isolation boundary there.
- The command does not remove parent directories, unrelated Utility scripts or auth JSON.
- It does not notify or disconnect a running CutAgent.lua process.
- Status aggregate `installed/current` covers either install variant; verify the individual row after removing only one variant.

## Stable public error codes

- `CONFIRMATION_REQUIRED`

## Examples

- `cutagent embedded uninstall --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
