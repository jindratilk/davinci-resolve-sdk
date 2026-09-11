# `color page node-cleanup`

Syntax: `cutagent color page node-cleanup [CLIP_NAME] [--mode VALUE]`

## Search terms

- remove empty Color nodes
- clean unused serial nodes
- delete blank grade nodes
- prune empty nodes
- clean node graph
- remove appended empty nodes
- collapse blank serial nodes
- tidy Color page nodes
- delete unused correction nodes

## What it does

Remove empty Color Page nodes.

## Do not use when

Use a dedicated node-delete operation or DaVinci Resolve UI when a nonempty node, mixer, branch, Power Window, OFX or deliberately configured “neutral-looking” node must be removed. Use reset/grade commands when the desired action is to clear parameters without changing topology. This command must not be used as a general graph optimizer.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--mode` (optional, default: `"empty-serial"`)

## Boundaries and gotchas

- With mixer types 68/90 present, only exact-empty serial nodes after the highest mixer node index are candidates.
- It does not render before/after, so unintended grade changes require independent visual/render proof.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent color page node-cleanup --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
