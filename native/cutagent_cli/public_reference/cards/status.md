# `status`

Syntax: `cutagent status [--include-ui]`

## Search terms

- is DaVinci Resolve running
- current project and timeline
- Studio or Free edition
- current DaVinci Resolve page
- project manager or open project
- blocked DaVinci Resolve modal

## What it does

Check DaVinci Resolve status.

## Public arguments and options

- `--include-ui` (optional, default: `false`) — Include the System Events UI probe. This can request macOS Automation permission.

## Boundaries and gotchas

- Studio external scripting must be reachable, or the embedded Free script/server must be installed, running, authenticated, and protocol-compatible.

## Examples

- `cutagent status --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
