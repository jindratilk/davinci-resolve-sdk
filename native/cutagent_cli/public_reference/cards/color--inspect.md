# `color inspect`

Syntax: `cutagent color inspect [CLIP_NAME] [--node-stack-layer VALUE]`

## Search terms

- inspect complete clip color state
- summarize grade and node graph
- diagnose clip color setup
- audit color correction on shot

## What it does

Inspect color state plus clip-attached Fusion grading state.

## Preflight and readback

After a color command, rerun and compare the specific owning section—node LUT/tools, CDL, versions, group, or Fusion graph—and pair it with a rendered frame for visual verification.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Boundaries and gotchas

- It does not include every Color-page parameter, keyframe, OpenFX setting, cache state, remote-grade scope detail, or external LUT/DCTL availability.

## Examples

- `cutagent color inspect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
