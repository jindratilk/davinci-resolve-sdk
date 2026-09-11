# `color node tools`

Syntax: `cutagent color node tools NODE_INDEX [--clip VALUE] [--node-stack-layer VALUE]`

## Search terms

- list tools in Color node
- inspect node effects
- see primary balance in node
- check LUT tool present
- show Color-page node categories
- verify node contains grade operations

## What it does

List nodes and effects present inside a color node.

## Do not use when

Use `color node graph` to correlate tools with labels/LUT/cache across all nodes, page-specific getters/setters for actual parameter values, and `clip fusion tools` for Fusion compositions. A returned category name is not sufficient to reproduce or verify a grade.

## Preflight and readback

Use before applying/removing a LUT, OFX or grade reset, and again afterward. Confirm expected additions/removals by exact returned name, then inspect parameter-specific state and render. Validate node count first if graph topology may have changed.

## Public arguments and options

- `NODE_INDEX` (required) — 1-based node index
- `--clip` (optional) — Clip name (current clip when omitted)
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Boundaries and gotchas

- Empty does not mean the node object was deleted.
- The wrapper validates one-based range.

## Examples

- `cutagent color node tools --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
