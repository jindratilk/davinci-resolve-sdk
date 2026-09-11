# `color node lut-get`

Syntax: `cutagent color node lut-get NODE_INDEX [--clip VALUE] [--node-stack-layer VALUE]`

## Search terms

- get LUT from Color node
- inspect assigned cube LUT
- verify node LUT set
- check whether grade node has LUT
- find DaVinci Resolve LUT key

## What it does

Read LUT path from a color node.

## Do not use when

This getter does not tell whether the referenced library file still exists or whether the node is enabled.

## Preflight and readback

Pair a nonempty key with `color node tools` (which should show a LUT tool), verify the installed file separately, and render because metadata readback does not prove pixels.

## Public arguments and options

- `NODE_INDEX` (required) — 1-based node index
- `--clip` (optional) — Clip name (current clip when omitted)
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Boundaries and gotchas

- Node indices are one-based current positions and version-specific graph context is not included in the response.

## Examples

- `cutagent color node lut-get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
