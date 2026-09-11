# `color primary set`

Syntax: `cutagent color primary set [--clip VALUE] [--comp VALUE] [--gain-r VALUE] [--gain-g VALUE] [--gain-b VALUE] [--gamma VALUE] [--saturation VALUE] [--master-gain VALUE]`

## Search terms

- set Fusion primary grade
- add ColorCorrector to a clip
- change RGB gain in Fusion
- adjust Fusion gamma
- desaturate clip with ColorCorrector
- change clip-attached saturation
- set master gain in Fusion comp
- create a primary ColorCorrector
- make clip monochrome in Fusion
- correct color through Fusion graph
- set red green blue channel gain

## What it does

Update a clip-attached Fusion ColorCorrector primary grade.

## Do not use when

Use `color page primary-set`, `color page wheel-set`, or other `color page` commands when the user means DaVinci Resolve Color page Lift/Gamma/Gain/Offset controls; this command creates a separate Fusion processing graph. Use `color cdl` for explicit ASC CDL slope/offset/power/saturation semantics. Use a specifically named `fusion tool configure` route if the intended ColorCorrector is not the first one.

## Preflight and readback

Validate that each requested raw Fusion value is finite and appropriate—this CLI does not do so.
For a newly created comp, also confirm the clip now owns the expected composition and that MediaOut shows the intended image.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index
- `--gain-r` (optional) — Red gain
- `--gain-g` (optional) — Green gain
- `--gain-b` (optional) — Blue gain
- `--gamma` (optional) — Master gamma
- `--saturation/--sat` (optional) — Saturation
- `--master-gain` (optional) — Master gain

## Boundaries and gotchas

- At least one must be present, but there is no requirement that it be finite or in a sensible domain.
- No numeric range or finiteness validation exists.
- Dry-run returns before clip and composition resolution.
- On a clip with zero comps, only requested comp 1 can be created.
- Higher indexes fail range validation rather than creating intervening comps.
- Agents must perform that equality check themselves.
- Without `--clip`, the current item or item under the playhead is used; a selected clip away from the playhead is not enough.
- `--saturation` and `--sat` are the same option.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color primary set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
