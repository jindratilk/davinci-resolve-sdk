# `clip dynamic-zoom`

Syntax: `cutagent clip dynamic-zoom [NAME] --start VALUE --end VALUE [--source-in VALUE] [--source-out VALUE] [--ease VALUE]`

## Search terms

- animate Ken Burns zoom on clip
- dynamic pan and zoom
- push in across shot
- zoom from one point to another
- Fusion transform keyframes
- animate center and size
- slow punch in on timeline clip

## What it does

Apply dynamic zoom through Fusion keyframes.

## Do not use when

Use Edit Inspector keyframes through `clip keyframe add` for supported Pan/Tilt/Zoom animation, or build/import a Fusion graph that explicitly connects MediaIn → Transform → MediaOut and creates a BezierSpline. Use static `clip transform` when only one scale/position is wanted.

## Preflight and readback

List existing Fusion comps and export comp 1 before mutation because this command always edits index 1. Use explicit `--source-in` and `--source-out`; preserve the intended source bounds and ensure out > in.

## Public arguments and options

- `NAME` (optional) — Clip name (or current clip)
- `--start` (required) — Start point x,y,zoom
- `--end` (required) — End point x,y,zoom
- `--source-in` (optional) — Source-domain in reference
- `--source-out` (optional) — Source-domain out reference
- `--ease` (optional, default: `"linear"`) — linear|in|out|inout

## Boundaries and gotchas

- A newly added tool therefore cannot affect pixels.
- Dry-run is genuinely non-mutating here.

## Examples

- `cutagent clip dynamic-zoom --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
