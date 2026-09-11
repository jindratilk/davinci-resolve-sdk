# `color page node-add`

Syntax: `cutagent color page node-add [CLIP_NAME] [--kind VALUE] [--position VALUE] [--node-index VALUE]`

## Search terms

- add Color page node
- create serial grade node
- append serial node
- add parallel node
- create Parallel Mixer
- add layer node
- create Layer Mixer
- make another correction node
- branch color grade

## What it does

Add a Color Page node using project.

## Do not use when

Use `node-cleanup` only to remove exact empty serial nodes, `node-label-set` to name an existing node, `node-enable-set` to bypass/enable it, and the relevant grading command to modify an existing node. Do not use parallel/layer add to extend an existing complex graph: these two routes only start from exactly one Color node. Do not use this for Fusion nodes; use `fusion comp tool-add` or a purpose-built Fusion command.

## Preflight and readback

Before mutation, confirm a local Disk project, exact timeline/clip, current node count and topology, and create a version/checkpoint for any valuable grade. For serial-before, confirm the target is within 1..node-count and that every node is serial. For parallel/layer, require exactly one existing node and active grade version. A count-only verification is not proof that a custom grade renders identically.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--kind/--type` (optional, default: `"serial"`)
- `--position` (optional, default: `"after"`)
- `--node-index/--node` (optional, default: `1`) — Target node index for --position before

## Boundaries and gotchas

- `--node-index` matters only for serial `--position before`.
- Serial-before is allowed only when every existing container has serial type 44.
- `--node 0` is silently normalized to 1 by `int(value or 1)` rather than rejected.
- Do not rely on zero as an invalid-input guard.

## Examples

- `cutagent color page node-add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
