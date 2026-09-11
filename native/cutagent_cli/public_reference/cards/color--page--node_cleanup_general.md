# `color page node-cleanup-general`

Syntax: `cutagent color page node-cleanup-general [CLIP_NAME] [--mode VALUE]`

## Search terms

- general node cleanup
- clean all empty nodes
- remove empty serial nodes
- prune blank grade nodes
- tidy Color graph
- remove unused Color nodes
- clean empty serials
- graph cleanup all
- delete blank appended nodes

## What it does

Remove empty Color Page nodes.

## Do not use when

Do not use `--mode all` to delete all unused nodes, mixers, branches, effects, masks or grades—it does none of those. For a known nonempty node, use a dedicated delete/reset command or manual Color-page graph editing after preserving the grade. Do not use this on Fusion graphs.

## Preflight and readback

Before running, enumerate the current Color nodes, identify exact empty serial candidates, save a grade/version checkpoint, and render a reference.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--mode` (optional, default: `"all"`) — Requested general graph cleanup mode

## Boundaries and gotchas

- The default `--mode all` is misleading: effective behavior is always `empty-serial`.
- It does not inspect or remove every unused node.
- Mixer graphs preserve mixer containers and only prune empty serial nodes whose index is beyond the highest mixer; branch empties are not cleaned.
- The dry-run message does not expose requested versus effective mode and cannot enumerate candidates.

## Examples

- `cutagent color page node-cleanup-general --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
