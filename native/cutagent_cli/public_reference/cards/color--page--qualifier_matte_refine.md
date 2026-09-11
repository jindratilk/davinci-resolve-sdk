# `color page qualifier-matte-refine`

Syntax: `cutagent color page qualifier-matte-refine [CLIP_NAME] [--hue VALUE] [--saturation VALUE] [--luma VALUE] [--blur-radius VALUE]`

## Search terms

- set qualifier hue center width softness symmetry
- set saturation key low high softness
- set luminance qualifier low high softness
- set matte blur radius without GUI
- refine Color key on Disk project
- deterministic qualifier parameter readback

## What it does

Refine a DaVinci Resolve Color Page HSL qualifier matte.

## Do not use when

Use `qualifier-gui-hsl-set` when preserving omitted GUI ranges, handling a wraparound Hue low/high range directly, or editing the current node through visible controls is required. Use `qualifier-sample` to measure a source pixel before choosing values.

## Preflight and readback

Before mutation, confirm a local Disk project, save it, identify the exact timeline item and active grade version, inspect whether node 2 already contains unrelated corrections, and save a grade/version checkpoint plus reference frame. Specify all three HSL groups when existing thresholds must be preserved rather than reset to defaults.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--hue` (optional)
- `--saturation` (optional) — Saturation low,high,low_soft,high_soft in UI units 0..100
- `--luma` (optional) — Luminance low,high,low_soft,high_soft in UI units 0..100
- `--blur-radius` (optional) — Matte Finesse Blur Radius in UI units 0..100

## Boundaries and gotchas

- Omitted groups are therefore reset to those full-range defaults, not preserved.
- There is no public `--node`, and an existing unrelated second node can receive qualifier parameters.
- Four numbers are required for every supplied H/S/L option.
- The command does not infer center/width from low/high values or vice versa.
- The active corrected version is updated; this command does not create an isolated grade version when one already exists.
- Duplicate clip names can make name-only targeting unsafe.
- Hue center/width/soft/symmetry must be translated deliberately.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page qualifier-matte-refine --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
