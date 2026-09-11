# `fusion effect transform`

Syntax: `cutagent fusion effect transform [--zoom VALUE] [--x VALUE] [--y VALUE] [--rotation VALUE]`

## Search terms

- transform Fusion composition
- move scale rotate Fusion image
- add Transform node inline
- zoom current Fusion comp
- offset MediaIn before MediaOut
- rotate Fusion output
- reposition Fusion graphic
- normalized Center coordinates
- shrink Fusion image
- pan Fusion node output
- add full-frame Transform tool
- stack Fusion transforms

## What it does

Add a transform effect inline.

## Do not use when

Use `clip transform` when geometry belongs to the Edit-page timeline item's Inspector rather than a Fusion node graph. That command targets a clip explicitly and exposes Edit transforms, crop, flips, opacity, composite mode, and reset behavior with a different coordinate contract.
Re-running this high-level command creates another node and composes its geometry with prior transforms.
This command applies to the whole connected image stream and creates no mask.
Do not interpret `--x` or `--y` as pixels, percentages, Edit-page Pan/Tilt units, or an absolute Center.
Do not use global dry-run for a non-mutating preview.
Do not run against an ambiguous active composition. The command has no clip, comp-index, tool-name, branch, frame-range, or time selector.

## Preflight and readback

Before execution, verify the active project, timeline, clip, and composition with `fusion comp current` and `fusion tool list`. Export the comp to capture current routing, and save a representative baseline frame with visible canvas boundaries.
Record whether transparent/out-of-frame areas and interpolation behavior are acceptable.
Inspect existing Transform nodes and determine whether the request is to edit one or intentionally stack another. Check branches, masks, multiple MediaOuts, current Fusion selection, and the existing source of MediaOut.
Compare actual values with the request because DaVinci Resolve can clamp them and the response only echoes inputs.
Export and visually inspect the same timeline frame. Confirm scale, position, angle, exposed canvas, crop, interpolation, and the unaffected surrounding timeline.
If the node is orphaned, connected to the wrong branch, or stacked unintentionally, delete it and explicitly reconnect the intended upstream source to MediaOut, or restore the saved comp. This command has no undo or cleanup.

## Public arguments and options

- `--zoom/-z` (optional, default: `1.0`) — Zoom factor (1.0 = 100%)
- `--x` (optional, default: `0.0`) — X offset from center
- `--y` (optional, default: `0.0`) — Y offset from center
- `--rotation/-r` (optional, default: `0.0`) — Rotation in degrees

## Boundaries and gotchas

- Global `--dry-run` is fully mutating.
- Only the first MediaIn and first MediaOut found are considered.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion effect transform --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
