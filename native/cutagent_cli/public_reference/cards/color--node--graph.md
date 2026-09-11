# `color node graph`

Syntax: `cutagent color node graph [--clip VALUE] [--node-stack-layer VALUE]`

## Search terms

- inspect full Color node graph summary
- list labels LUTs tools cache
- compare node graph before after
- show node count and effects
- inspect Color-page node contents
- verify grade reset metadata

## What it does

Read node-graph summary with labels, LUTs, nodes, and cache modes.

## Preflight and readback

Capture this summary before graph-wide reset or a sequence of label/LUT/cache mutations. Afterward compare node count and each field, then verify the specialized field and render a representative frame. If any row has unexpected empty/default values, rerun its individual getters because this aggregate suppresses per-field exceptions.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Boundaries and gotchas

- It does not return node enabled/bypass state; disable/enable can change pixels while this summary remains identical.

## Examples

- `cutagent color node graph --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
