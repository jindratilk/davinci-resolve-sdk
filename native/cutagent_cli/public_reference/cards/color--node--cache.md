# `color node cache`

Syntax: `cutagent color node cache NODE_INDEX [--mode VALUE] [--clip VALUE] [--node-stack-layer VALUE]`

## Search terms

- get node cache mode
- enable node cache
- disable Color node cache
- set cache to Auto
- force grade node caching
- troubleshoot node render cache

## What it does

Check node cache mode.

## Do not use when

Cache Enabled is not evidence that a cache frame currently exists or is valid.

## Preflight and readback

For performance work, separately inspect/cache-render status and playback behavior. Restore Auto after a diagnostic override unless the workflow explicitly requires forced enable/disable.

## Public arguments and options

- `NODE_INDEX` (required) — 1-based node index
- `--mode` (optional) — -1=auto, 0=disabled, 1=enabled
- `--clip` (optional) — Clip name (current clip when omitted)
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Boundaries and gotchas

- The lifecycle required separate gets to prove `1`, then `0`, then `-1`.
- Dry-run validates node/mode and does not mutate.

## Examples

- `cutagent color node cache --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
