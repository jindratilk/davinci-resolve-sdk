# `color page alpha-output-connect`

Syntax: `cutagent color page alpha-output-connect CLIP_NAME [--track VALUE] [--at VALUE] [--node-index VALUE]`

## Search terms

- add Color Page Alpha Output
- connect blue key output
- connect Magic Mask alpha
- make foreground clip transparent
- finish text behind object matte
- route node key to alpha
- isolate Magic Mask foreground

## What it does

Connect a Color node to Alpha Output.

## Do not use when

Use `color page magic-mask-draw-stroke` first to create and track the Color-page Magic Mask. Do not use this command on parallel/layer/multi-node Color graphs, on a clip without an existing grade body, or as a generic node-graph editor. Do not treat its successful topology readback as proof that a text-behind-object composite is visually correct.

## Preflight and readback

Before running, verify the exact active timeline, uniquely named upper foreground duplicate, video track, crossing time, and that its Color graph has exactly one node containing the intended tracked Magic Mask. Afterward, require the project and timeline to reopen correctly, then export V3-only early/middle/late frames and all-on comparison frames. The foreground-only frames must show the complete intended subject over transparency or black/checkerboard; also export one foreground-off frame proving that the upper matte creates the occlusion.

## Public arguments and options

- `CLIP_NAME` (required) — Exact clip name on the active timeline
- `--track` (optional) — Exact 1-based video track selector
- `--at` (optional) — Exact timeline position selector
- `--node-index/--node` (optional, default: `1`) — Color node whose key output feeds Alpha Output

## Boundaries and gotchas

- `--track` and `--at` are mandatory.
- Missing, duplicate, or inconsistent ownership fails before the grade version is updated.
- A detail-only or background-heavy Magic Mask can still be visually wrong.

## Examples

- `cutagent color page alpha-output-connect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
