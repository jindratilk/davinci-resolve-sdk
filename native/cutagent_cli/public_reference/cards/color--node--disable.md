# `color node disable`

Syntax: `cutagent color node disable NODE_INDEX [--clip VALUE] [--node-stack-layer VALUE]`

## Search terms

- disable Color node
- bypass grade node
- turn off node correction
- compare graded versus ungraded
- mute Color-page node
- temporarily remove node effect
- troubleshoot which node changes image

## What it does

Disable a color node.

## Do not use when

Use `color node reset` to erase grade state, node-delete operations to remove topology, LUT clear to remove only a LUT, and clip-level color bypass commands when the entire grade should be bypassed.

## Preflight and readback

Record node index/metadata and render a representative frame. Since no enabled getter exists in this command family, pixel proof or UI/node-state inspection is the meaningful verification.

## Public arguments and options

- `NODE_INDEX` (required) — 1-based node index
- `--clip` (optional) — Clip name (current clip when omitted)
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Boundaries and gotchas

- Do not infer enabled state from metadata.
- Dry-run validated the target and did not change pixels/state.

## Examples

- `cutagent color node disable --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
