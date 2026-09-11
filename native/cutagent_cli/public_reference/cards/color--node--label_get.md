# `color node label-get`

Syntax: `cutagent color node label-get NODE_INDEX [--clip VALUE] [--node-stack-layer VALUE]`

## Search terms

- get Color node label
- inspect grade node label
- verify node rename
- find Color-page node title

## What it does

Read label for a color node.

## Do not use when

Use `color node label-set` to change the label, `color node list/graph` to see all nodes, and Fusion tool naming commands for clip-attached Fusion nodes.

## Preflight and readback

Pair the label with clip unique ID, version and current node index when recording long-lived references.

## Public arguments and options

- `NODE_INDEX` (required) — 1-based node index
- `--clip` (optional) — Clip name (current clip when omitted)
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Boundaries and gotchas

- It does not identify local versus remote Color version in the response.
- Omitting `--clip` uses current-item context.

## Examples

- `cutagent color node label-get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
