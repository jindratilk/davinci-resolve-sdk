# `color window reorder`

Syntax: `cutagent color window reorder ORDER [--clip VALUE] [--comp VALUE]`

## Search terms

- reorder grading windows
- change mask stack order
- move Fusion window before another window
- reverse power window order
- rearrange rectangle and ellipse masks
- change EffectMask chain order
- put polygon mask first
- reorder active color masks
- change window compositing sequence
- sort clip grading windows

## What it does

Reorder active windows inside the mask stack.

## Do not use when

Use `color window attach` to add an existing orphan window to the active chain, or `color window detach` to remove one while preserving its tool. `reorder` refuses both operations because its requested set must exactly equal the current active-window set. Use `color window rectangle`, `ellipse` or `polygon` to create a shape, and a Fusion input-edit operation to alter an existing shape's geometry.
Do not use this command to reorder qualifiers or trackers; their relative order is not an argument here. Do not use it for Color-page Power Windows: these “windows” are Fusion mask tools attached to a Fusion ColorCorrector.

## Preflight and readback

Preserve exact case. A dry-run is useful only for parsing the string; it does not resolve the clip, comp or current active set.
Check that custom main-pipe effects were not displaced before saving the project.

## Public arguments and options

- `ORDER` (required) — Comma-separated window tool names in desired order
- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- Whitespace around names is stripped; matching remains case-sensitive.
- The list must exactly match all active windows.
- A window that exists in the comp but is currently orphaned is “unknown” for this command because only the chain traced backward from the primary ColorCorrector is eligible.
- Duplicate names are rejected before connecting to DaVinci Resolve.
- Dry-run does not perform the exact-set check.
- The command does not verify window geometry or pixels.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color window reorder --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
