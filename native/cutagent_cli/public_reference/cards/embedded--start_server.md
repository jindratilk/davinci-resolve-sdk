# `embedded start-server`

Syntax: `cutagent embedded start-server [--host VALUE] [--port VALUE] [--request-timeout-s VALUE]`

## Search terms

- start embedded bridge broker
- make CutAgent.lua connect
- launch Lua command broker
- fix embedded bridge not running
- listen on CutAgent bridge port
- run DaVinci Resolve Free bridge

## What it does

Start CutAgent support for DaVinci Resolve.

## Do not use when

Use `embedded status` or `embedded ping` when a broker may already be running. Starting the broker alone does not load Lua; after startup, run Workspace > Scripts > CutAgent in DaVinci Resolve.
Do not use a non-loopback host; the embedded bridge intentionally rejects network exposure.

## Preflight and readback

Choose a request timeout large enough for renders/imports but bounded for recovery.
After launch, keep the foreground process supervised. On shutdown, verify the server stopped and its auth file disappeared.

## Public arguments and options

- `--host` (optional) — Host to bind
- `--port` (optional, default: `18744`) — Port to bind
- `--request-timeout-s` (optional) — Lua request timeout

## Boundaries and gotchas

- Global `--dry-run` is not consulted.
- Status/ping must still prove the broker socket.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent embedded start-server --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
