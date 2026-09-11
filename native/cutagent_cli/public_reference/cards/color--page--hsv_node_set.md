# `color page hsv-node-set`

Syntax: `cutagent color page hsv-node-set [CLIP_NAME] [--node-index VALUE] [--gamma-r VALUE] [--gamma-g VALUE] [--gamma-b VALUE] [--gamma-master VALUE] [--gain-r VALUE] [--gain-g VALUE] [--gain-b VALUE] [--gain-master VALUE] [--key-output-gain VALUE]`

## Search terms

- HSV saturation node workflow
- set node color space to HSV
- channel 2 saturation trick
- HSV Gamma Gain saturation
- tutorial HSV node
- increase saturation in HSV
- control HSV look strength

## What it does

Runs the public `color page hsv-node-set` CutAgent command.

## Do not use when

Use normal `wheel-set`/`primary-set` for RGB primaries, `color page sat-curve-set` or `color hue-sat` for more conventional saturation shaping, and node-add/topology commands when preserving a multi-node graph.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`)
- `--gamma-r` (optional)
- `--gamma-g` (optional)
- `--gamma-b` (optional)
- `--gamma-master` (optional)
- `--gain-r` (optional)
- `--gain-g` (optional)
- `--gain-b` (optional)
- `--gain-master` (optional)
- `--key-output-gain/--strength` (optional) — Optional Key Output Gain/strength applied after HSV node, 0..1

## Boundaries and gotchas

- Omitting wheel options does not preserve current values.
- Only node 1 is supported.
- Wheel overrides are checked only for finiteness; there are no min/max bounds.
- `--strength` is a separate second commit/reopen, not part of one atomic mutation.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent color page hsv-node-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
