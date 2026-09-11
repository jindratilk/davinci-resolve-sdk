# `color page resolvefx-param-list`

Syntax: `cutagent color page resolvefx-param-list [CLIP_NAME] [--node-index VALUE] [--fx VALUE]`

## Search terms

- list current ResolveFX parameters
- see which ResolveFX is on node
- verify ResolveFX plugin ID on clip
- find existing parameter type for auto write
- inspect active ResolveFX version

## What it does

List decoded DaVinci Resolve effects OFX options on a clip Color Page node.

## Do not use when

Use `resolvefx-list` for all installed effects. Use `resolvefx-param-set` to change a value and require rendered proof, and `color page read` for broader grade/node/curve/window state. Do not use this readback as visual acceptance of an earlier write.

## Preflight and readback

Before reading, save the project if the GUI has recent unsaved option changes, identify the exact timeline item and node, and prefer `--fx` as a wrong-effect guard. Follow any mutation with a fresh param list and rendered comparison.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index containing the ResolveFX OFX tool
- `--fx` (optional) — Optional current ResolveFX name/plugin id guard

## Boundaries and gotchas

- It supports local Disk projects only.
- `--fx` is a guard, not a selector.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page resolvefx-param-list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
