# `fusion mask ellipse`

Syntax: `cutagent fusion mask ellipse [--center VALUE] [--width VALUE] [--height VALUE] [--softness VALUE]`

## Search terms

- add ellipse mask Fusion
- create oval EffectMask
- Fusion EllipseMask node
- circular mask Fusion composition
- set ellipse center width height
- soften ellipse mask edge
- isolate oval image region
- connect EllipseMask to EffectMask
- ellipse mask orphan node
- ellipse auto-connect selection
- chain Fusion ellipse masks
- negative ellipse width clamp

## What it does

Add an ellipse mask.

## Do not use when

Do not run when the active Fusion composition is uncertain. This command has no project, timeline, clip, track, record-frame, composition-index, or existing-node selector.
Do not assume success means the image was masked. Explicitly connect the generated mask to the intended tool and verify the graph plus output frame.
Do not assume the node is safely orphaned. Current Fusion selection can cause DaVinci Resolve to auto-connect it as another mask's EffectMask or to a selected image/effect tool.
Use `fusion mask rectangle` for a box, `fusion mask polygon` for a supplied point path, or a suitable spline/paint/tracker workflow for freeform roto, animation, tracking, gradients, or complex compound masks.
Re-running the high-level command always adds a new node.
Do not rely on CLI range checking for geometry.

## Preflight and readback

Before execution, inspect `status`, `fusion comp current`, and `fusion tool list`.
Identify the currently selected Fusion node.
Validate center syntax and normalized geometry with dry-run first. A malformed center returns a structured validation error without creating a node.
For a visual task, export the same frame with and without the connected mask.
If testing leaves a mask chain, delete nodes in reverse order or disconnect exact target inputs first.

## Public arguments and options

- `--center/-c` (optional, default: `"0.5,0.5"`) — Center X,Y
- `--width/-w` (optional, default: `0.5`) — Width
- `--height` (optional, default: `0.5`) — Height
- `--softness/-s` (optional, default: `0.0`) — Soft edge

## Boundaries and gotchas

- Center must use `x,y`.
- The success JSON cannot distinguish orphaned, image-connected, or chained outcomes.
- There is no CLI range validation for center, width, height, or softness.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion mask ellipse --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
