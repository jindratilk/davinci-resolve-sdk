# `color page node-add-topology`

Syntax: `cutagent color page node-add-topology [CLIP_NAME] [--topology VALUE] [--position VALUE]`

## Search terms

- add node topology
- add serial topology
- create parallel topology
- create layer mixer topology
- add mixer node layout
- branch Color page graph
- add node before selected grade
- build Color node graph

## What it does

Runs the public `color page node-add-topology` CutAgent command.

## Do not use when

Use grading/label/enable commands for an existing node, cleanup for exact empty serial nodes, and Fusion tool commands for a Fusion flow. Do not use the `mixer` alias when you want a Parallel Mixer—it maps to the layer route; say `parallel` or `parallel-mixer` instead. For inserting a branch into an already complex graph, this command is not supported.

## Preflight and readback

Before running, inspect the exact target clip's node graph and translate the requested placement deliberately: never assume `selected` discovers the GUI selection. Confirm serial-only topology for any before/node-N insertion and exactly one current node for parallel/layer. Back up or checkpoint valuable grades.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--topology` (optional, default: `"serial"`) — Node topology to add: serial, parallel, layer, or mixer
- `--position` (optional, default: `"after"`) — Insertion position: after, before, selected, or node-N

## Boundaries and gotchas

- `--position selected` is only an alias for `after`; no selected-node query occurs.
- Bare `--position before` targets node 1.
- It cannot prove semantic branch order or visual equivalence on a custom grade by itself.

## Examples

- `cutagent color page node-add-topology --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
