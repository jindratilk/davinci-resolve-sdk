# `color node reset`

Syntax: `cutagent color node reset [--clip VALUE] [--node-stack-layer VALUE] [--force]`

## Search terms

- reset all Color grades
- remove clip color correction
- wipe labels LUTs and node tools
- return clip to ungraded image
- reset Color-page nodes
- clear entire grade graph

## What it does

Reset all grades on node graph.

## Do not use when

Use Fusion reset for clip-attached Fusion grading helpers.

## Preflight and readback

Export/back up the grade (DRX/still/project), capture full node graph, active version/group context and a rendered frame. In JSON mode pass `--force`. Verify other versions/groups separately because the response does not enumerate affected scope.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index
- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- There is no node-index argument and no command-specific dry-run preview.
- Node count remained one, so count-only verification would miss the destructive change.

## Stable public error codes

- `CONFIRMATION_REQUIRED`

## Examples

- `cutagent color node reset --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
