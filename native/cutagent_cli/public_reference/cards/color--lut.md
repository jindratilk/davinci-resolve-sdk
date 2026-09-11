# `color lut`

Syntax: `cutagent color lut [CLIP_NAME] [--node VALUE] [--set VALUE] [--clear] [--node-stack-layer VALUE]`

## Search terms

- apply LUT to color node
- set cube on clip grade
- clear LUT from node
- install and attach local LUT file
- inspect LUT key on Color node

## What it does

Check a LUT on a color node.

## Do not use when

Use `color lut-refresh` only to rescan an already installed library, `color page lut-library-import` for an explicitly managed library import, and `color export-lut`/`color curves`/`color huesat` to create LUT files. Use DRX/grade-copy when the desired look includes more than a node LUT.

## Preflight and readback

After clear, require empty node readback and a rendered reversal; separately remove the unique library file and refresh when it should no longer be installed.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node` (optional, default: `1`) — Node index
- `--set` (optional) — LUT file path to apply
- `--clear` (optional, default: `false`) — Clear LUT from node
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Boundaries and gotchas

- Clear only detaches the node.
- It only echoes path/node.
- The set response hides installation attempts/root/path and returns only requested path plus node readback, even though the lower layer may try system/user roots and several keys.
- `--set` and `--clear` are mutually exclusive; node must be positive.

## Examples

- `cutagent color lut --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
