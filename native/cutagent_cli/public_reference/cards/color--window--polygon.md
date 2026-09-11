# `color window polygon`

Syntax: `cutagent color window polygon POINTS [--clip VALUE] [--comp VALUE]`

## Search terms

- add polygon grading window
- create custom shape Fusion mask
- draw freeform color correction mask
- isolate object with polygon
- make PolylineMask from points
- add four-point grading region
- custom outline mask for ColorCorrector
- create offscreen polygon matte
- mask irregular subject
- add Fusion polygon window
- define mask vertices by coordinates

## What it does

Add a polygon grading window using Fusion mask.

## Preflight and readback

Before invoking, parse and visualize the intended normalized coordinates, require at least three distinct non-collinear vertices, and export/back up the Fusion comp. The CLI itself checks only formatting/count/finiteness, not bounds, closure, uniqueness or area.
Afterward, ignore echoed `points` as proof. Export the comp and inspect the associated BezierSpline/Polyline keyframe for actual vertices, then view/render the matte. Also inspect the full mask chain because the tool is connected even when geometry is empty and global canonicalization can reactivate/rewrite other helpers.

## Public arguments and options

- `POINTS` (required) — Points as 'x,y;x,y;...'
- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- The validator does not require the final point to repeat the first, does not close the shape explicitly, and does not reject duplicate, collinear, self-intersecting or zero-area point sets.
- Each coordinate must be finite numeric text.
- A Color version does not protect Fusion comp changes.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color window polygon --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
