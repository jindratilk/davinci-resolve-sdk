# `color node enable`

Syntax: `cutagent color node enable NODE_INDEX [--clip VALUE] [--node-stack-layer VALUE]`

## Search terms

- enable Color node
- turn grade node back on
- unbypass node correction
- restore node effect
- activate Color-page node
- re-enable LUT or grade node
- undo node disable

## What it does

Enable a color node.

## Do not use when

Use cache mode Enabled only to force caching, not to activate image processing. Use grade restore/import when the node was reset/deleted rather than merely bypassed, and Fusion tool controls for clip-attached Fusion graphs.

## Preflight and readback

Confirm the correct clip/node and ideally capture the disabled frame. Enable, then render the identical frame and compare against a known enabled baseline.

## Public arguments and options

- `NODE_INDEX` (required) — 1-based node index
- `--clip` (optional) — Clip name (current clip when omitted)
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Boundaries and gotchas

- The response does not distinguish a state transition from an idempotent no-op.
- Dry-run is non-mutating but likewise cannot tell whether the node is currently enabled.

## Examples

- `cutagent color node enable --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
