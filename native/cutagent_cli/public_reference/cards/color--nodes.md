# `color nodes`

Syntax: `cutagent color nodes [CLIP_NAME] [--node-stack-layer VALUE]`

## Search terms

- list Color page nodes
- inspect node count and labels
- show LUTs on grade nodes
- see tools used by each color node

## What it does

Check color node graph info.

## Do not use when

Use `color inspect` for CDL, versions, group and clip-attached Fusion grading in one aggregate; `color node graph`/node-specific commands for enabled state and richer topology; and `color graph inspect` for Fusion connections.

## Preflight and readback

Run before a node mutation to record count/order/labels/LUT/tools/cache and again afterward to compare the owning field. Pair a LUT/tool change with the specialized getter and a render. If any row contains empty defaults unexpectedly, use the specialized node commands because this aggregate suppresses individual getter exceptions.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Boundaries and gotchas

- It does not report node enabled/bypassed state, serial/parallel/layer topology, keyframes, parameter values, windows, qualifiers, trackers, DCTL/OpenFX parameters, or graph connections.
- Node indices are current one-based graph positions and can change after node insertion/deletion/reordering.

## Examples

- `cutagent color nodes --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
