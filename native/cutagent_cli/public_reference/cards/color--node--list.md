# `color node list`

Syntax: `cutagent color node list [--clip VALUE] [--node-stack-layer VALUE]`

## Search terms

- list Color page nodes
- show node labels LUT cache
- count clip grade nodes
- enumerate serial grade nodes
- check node index before mutation
- see LUT and cache on each node

## What it does

List color nodes for a clip.

## Do not use when

Use `color node graph` when tools are also needed, specialized label/LUT/cache getters when a failure must not be hidden, and `color nodes` for the older aggregate whose field naming differs slightly.

## Preflight and readback

Run before any node-indexed mutation to capture count and current indices. After label/LUT/cache/reset operations, run again and compare the owning field, then use the specialized getter for authoritative failure reporting. Pair visible grade changes with a rendered frame because list metadata does not include primary parameter values or pixels.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Boundaries and gotchas

- Node indices are one-based current positions, not stable node IDs.
- Node existence therefore does not imply any active correction.
- Omitting `--clip` relies on current-item context.

## Examples

- `cutagent color node list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
