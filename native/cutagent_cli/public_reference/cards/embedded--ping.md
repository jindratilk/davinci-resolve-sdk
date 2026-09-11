# `embedded ping`

Syntax: `cutagent embedded ping`

## Search terms

- ping embedded bridge
- is CutAgent broker reachable
- verify CutAgent.lua is connected
- diagnose embedded bridge not running
- test embedded authentication
- confirm DaVinci Resolve Lua client

## What it does

Check the CutAgent connection to DaVinci Resolve.

## Do not use when

Use `embedded status` when installation hashes, both standard/sandbox script locations, legacy files and auth-file health are also needed. Use `embedded install` when the installed script/protocol is stale. Use `embedded start-server` when the broker is absent, then launch Workspace > Scripts > CutAgent when the broker runs but `connected:false`.
Run the relevant read-only command after ping.

## Preflight and readback

If `connected:false`, keep the broker running and reload CutAgent.lua. Prove real readiness with a small read-only embedded command.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Host validation only permits loopback.
- `--dry-run` does not suppress the read-only socket request.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent embedded ping --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
