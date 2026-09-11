# `fusion effect color-correct`

Syntax: `cutagent fusion effect color-correct [--gain-r VALUE] [--gain-g VALUE] [--gain-b VALUE] [--gamma VALUE] [--saturation VALUE]`

## Search terms

- color correct Fusion composition
- add ColorCorrector node
- adjust RGB gain Fusion
- change Fusion gamma saturation
- color grade current Fusion comp
- add inline ColorCorrector
- tint Fusion image
- desaturate Fusion output
- correct MediaIn before MediaOut
- Fusion gain-r ignored
- MasterRedGain ColorCorrector
- MasterRGBGamma Fusion

## What it does

Add a ColorCorrector effect inline.

## Do not use when

Use `color page primary-set` or the appropriate Color-page command when the correction belongs to DaVinci Resolve's Color-page grade, node tree, color-managed grading order, remote/local versions, or finishing workflow. This command only changes a Fusion composition graph.
Re-running this high-level command creates another identity node and can add graph clutter; if any nodes are later configured, their corrections compose serially.
This command creates no qualifier, power window, mask, tracker, matte, key, or secondary isolation.
Use explicit ColorCorrector controls when lift, contrast, tonal ranges, output levels, hue, tint, curves, channel processing, clipping mode, blend, or color-space-aware behavior matters.
Do not use global dry-run for a safe preview.
Do not run against an ambiguous active composition. There is no clip, composition index, tool, branch, frame range, or time selector.

## Preflight and readback

Before execution, verify active project, timeline, clip, and composition with `fusion comp current` and `fusion tool list`. Export the comp to preserve topology and capture a color-rich representative baseline frame.
Decide whether the request belongs in Fusion or the Color page, and account for color-management/order implications. Inspect existing ColorCorrectors, masks, multiple MediaOuts, branches, and the current source feeding MediaOut.
Treat dry-run and errors as potentially mutating.
Then export the same frame and compare it with baseline. A connected ColorCorrector is not evidence that the requested grade was applied.
If the command left an identity or orphaned node, delete it and reconnect the intended source to MediaOut, or restore the saved comp.

## Public arguments and options

- `--gain-r` (optional, default: `1.0`) — Red gain
- `--gain-g` (optional, default: `1.0`) — Green gain
- `--gain-b` (optional, default: `1.0`) — Blue gain
- `--gamma` (optional, default: `1.0`) — Master gamma
- `--saturation/--sat` (optional, default: `1.0`) — Saturation

## Boundaries and gotchas

- Global `--dry-run` is mutating.
- Only the first MediaIn and first MediaOut found are considered.
- There is no input range validation.
- `--saturation` and `--sat` are exact aliases.
- The command does not switch pages, restore UI selection, preserve the selected node, checkpoint the comp, render proof, or roll back invalid parameter writes.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion effect color-correct --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
