# `color page power-window-gradient`

Syntax: `cutagent color page power-window-gradient [CLIP_NAME] [--node-index VALUE] [--size VALUE]`

## Search terms

- add gradient Power Window
- linear gradient mask
- graduated color mask
- soft transition window
- darken sky with gradient
- top-to-bottom Color mask
- create Gradient window
- feathered directional mask
- node-local gradient matte
- graduated filter effect

## What it does

Update a Color Page Gradient Power Window using project readback.

## Do not use when

Use `power-window-gradient-transform` when starting from GUI-scale softness and/or changing pan/tilt on the first/root Gradient; use `power-window-gui-set` when angle or other visible GUI fields need the supported GUI controls (with its own targeting caveats). Use `power-window-linear` for a four-sided linear/rectangle-style window with width/height and independent softness controls. Use a Curve/Polygon for explicit boundary vertices.

## Preflight and readback

Run the transform or GUI command for placement, and tracking separately if needed.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index; create/use an empty local node for secondaries
- `--size` (optional, default: `200.0`)

## Boundaries and gotchas

- Re-running without `--size` writes 200 and can reset an existing Gradient's softness.
- Range validation occurs after the dry-run early return.
- This command cannot set angle, pan or tilt.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page power-window-gradient --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
