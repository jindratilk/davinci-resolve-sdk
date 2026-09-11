# `color cdl`

Syntax: `cutagent color cdl [ACTION_OR_CLIP] [MAYBE_CLIP] [--node VALUE] [--slope VALUE] [--offset VALUE] [--power VALUE] [--sat VALUE]`

## Search terms

- set ASC CDL values
- apply CDL color correction
- change SOP Sat on color node
- inspect primary CDL grade
- set node color transform numerically
- lift gamma gain as CDL
- verify CDL with rendered frame

## What it does

Set CDL values through DaVinci Resolve with rendered-frame proof.

## Do not use when

Use `color page primary-set` or `color wheels set` for their documented primary-control models, `color grade-apply` for an entire DRX node grade, and `color lut` for a LUT.

## Preflight and readback

Use dry-run to validate syntax without capturing frames or connecting. For higher nodes, inspect the Color graph and render because getter reconstruction is limited to node 1.

## Public arguments and options

- `ACTION_OR_CLIP` (optional) — Optional action ('get'/'set') or clip name
- `MAYBE_CLIP` (optional) — Clip name when using legacy syntax: color cdl get/set <clip>
- `--node` (optional, default: `1`) — Node index
- `--slope` (optional) — Slope as 'R G B' (e.g., '1.0 0.9 0.8')
- `--offset` (optional) — Offset as 'R G B'
- `--power` (optional) — Power as 'R G B'
- `--sat` (optional) — Saturation

## Boundaries and gotchas

- Triplets accept spaces or commas and are normalized to floats, but there are no value-range constraints for slope, offset, power, or saturation beyond numeric parsing.

## Examples

- `cutagent color cdl --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
