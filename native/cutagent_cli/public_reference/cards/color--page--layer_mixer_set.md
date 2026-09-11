# `color page layer-mixer-set`

Syntax: `cutagent color page layer-mixer-set [CLIP_NAME] [--node-index VALUE] [--mode VALUE] [--opacity VALUE]`

## Search terms

- set Layer Mixer Overlay
- change layer composite mode
- fade Layer Mixer branch
- branch opacity
- normal vs overlay Color nodes
- blend parallel Color node
- adjust mixer input strength
- set node key for layer branch

## What it does

Runs the public `color page layer-mixer-set` CutAgent command.

## Do not use when

Use `node-add-topology` or the fixed `bleach-bypass-set` when a Layer Mixer graph first needs to be created. Use `key-output-set` for the first ordinary Color node outside a known layer branch, and Edit-page opacity/composite commands for timeline clips.

## Preflight and readback

Before running, inspect graph edges and identify the one-based branch node feeding the desired mixer—the `--node` value is the branch, not the mixer node. Export the grade and record current mode/Key Output.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `2`) — 1-based layer node index feeding the Layer Mixer
- `--mode` (optional, default: `"Overlay"`) — Layer Mixer composite mode
- `--opacity` (optional) — Layer Mixer branch opacity, 0..100

## Boundaries and gotchas

- `--node` names the layer/branch node whose outgoing edge identifies a mixer.
- Only Normal and Overlay validate.
- It does not repair or create topology.

## Examples

- `cutagent color page layer-mixer-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
