# `color node label-set`

Syntax: `cutagent color node label-set NODE_INDEX LABEL [--clip VALUE] [--node-stack-layer VALUE]`

## Search terms

- label Color node
- rename grade node
- set node name
- annotate serial node
- name Color-page correction node
- organize node graph labels

## What it does

Runs the public `color node label-set` CutAgent command.

## Do not use when

Use Fusion tool naming for clip-attached Fusion nodes, group rename for Color groups, and version rename for grade versions. Do not use a label change to identify or reorder a node; node index remains positional and label uniqueness is not enforced.

## Preflight and readback

Dry-run first if desired.

## Public arguments and options

- `NODE_INDEX` (required) — 1-based node index
- `LABEL` (required) — Label to assign to the node
- `--clip` (optional) — Clip name (current clip when omitted)
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Boundaries and gotchas

- Do not bypass that scope check.

## Examples

- `cutagent color node label-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
