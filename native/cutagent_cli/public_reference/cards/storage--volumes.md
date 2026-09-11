# `storage volumes`

Syntax: `cutagent storage volumes`

## Search terms

- list Media Storage volumes
- DaVinci Resolve mounted roots
- media browser storage paths
- available import volumes
- storage root discovery
- Resolve MediaStorage mounts
- mounted volume path list
- browseable storage roots

## What it does

List mounted storage volumes.

## Do not use when

Do not assume every OS-mounted disk or network share appears; the result reflects DaVinci Resolve's Media Storage configuration.
Do not treat a listed root as proof of readability, writeability, free space, online media, or project access.

## Preflight and readback

Before execution, ensure the embedded bridge is running.
After changing DaVinci Resolve Media Storage preferences or mounts, rerun the command and compare exact paths/order.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The result is not required to be a list.
- No scope/source label identifies why a root is mounted.
- The command does not report capacity, free space, permissions, reachability, or media count.
- It does not distinguish local, removable, network, cloud, or disconnected volumes.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent storage volumes --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
