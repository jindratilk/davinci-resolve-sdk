# `color page cst-set`

Syntax: `cutagent color page cst-set [CLIP_NAME] [--node-index VALUE] [--input-color-space VALUE] [--input-gamma VALUE] [--output-color-space VALUE] [--output-gamma VALUE] [--require-render-proof]`

## Search terms

- Color Space Transform
- add CST node effect
- convert log to Rec.709
- change input gamma
- transform camera gamut
- ResolveFX CST
- DaVinci Wide Gamut conversion
- input output color space and gamma

## What it does

Update DaVinci Resolve effects Color Space Transform using project and rendered-frame proof.

## Do not use when

Use project/timeline color-management settings for a managed workflow affecting many clips, `color page cat-set` for a Fusion Chromatic Adaptation between white illuminants, or `color lut`/`dctl-apply` for a LUT/DCTL transform. Use `color page resolvefx-remove` to remove an OFX; this command has no clear/remove mode.

## Preflight and readback

Before mutation, inspect the target node and discover/list its ResolveFX tools, capture current project color management, and choose exact registry-supported labels/tokens. Re-list ResolveFX on that same node and visually inspect the conversion for clipping or double transforms.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index to receive/update the CST OFX tool
- `--input-color-space` (optional) — Input color space label or DaVinci Resolve token
- `--input-gamma` (optional) — Input gamma label or DaVinci Resolve token
- `--output-color-space` (optional) — Output color space label or DaVinci Resolve token
- `--output-gamma` (optional) — Output gamma label or DaVinci Resolve token
- `--require-render-proof/--setup-only` (optional, default: `true`) — Export before/after Color Page frames and fail unless the rendered image changes.

## Boundaries and gotchas

- This changes an OFX tool inside one Color node; it does not change project color science or tag media input color space.
- At least one of the four CST options is required.
- Multiple CST OFX tools on the same node are an explicit ambiguous error.
- Insertion appends a CST tool entry to the node's existing tool block; it does not reorder other ResolveFX.
- Actual CLI parsing coerces `--node 0` to node 1 because the wrapper applies `or 1` before positivity validation.
- Treat zero as a dangerous alias, not a valid zero-based index.
- The target Color node must already exist and have a grade/version body.
- The command does not add a Color node for an out-of-range index.

## Examples

- `cutagent color page cst-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
