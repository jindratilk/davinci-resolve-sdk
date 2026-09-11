# `fusion mask rectangle`

Syntax: `cutagent fusion mask rectangle [--center VALUE] [--width VALUE] [--height VALUE] [--softness VALUE]`

## Search terms

- add rectangle mask Fusion
- create rectangular EffectMask
- mask Fusion tool with box
- Fusion RectangleMask node
- set rectangle center width height
- soften rectangle mask edge
- crop image with Fusion mask
- connect RectangleMask to MediaIn
- rectangle mask auto-connect selection
- rectangle mask outside frame
- negative rectangle width Fusion
- SoftEdge clamp Fusion

## What it does

Add a rectangle mask.

## Do not use when

Do not use this command when the target composition is ambiguous. It has no project, timeline, clip, track, record-frame, composition-index, or existing-tool selector; it always acts on the composition currently resolved by Fusion.
Do not assume the new mask affects the image.
Do not assume the new mask is orphaned either. DaVinci Resolve may auto-connect it based on the currently selected node.
Re-running this command always adds another node and can extend an unintended mask chain.
Do not use unvalidated out-of-range geometry as a portable clipping strategy. The CLI accepts center and dimensions outside the normal frame range.

## Preflight and readback

Before execution, verify the active project, timeline, clip, and composition with `status`, `fusion comp current`, and `fusion tool list`. Export the composition if the existing graph or node selection matters.
Inspect which Fusion tool is currently selected.
Validate normalized geometry deliberately. Decide whether values outside that range are intentional rather than assuming the command clamps them.
Use global dry-run to validate parsing and see the exact requested values without touching DaVinci Resolve.
A tool list alone cannot reveal whether DaVinci Resolve automatically attached the mask to the selected tool or chained it through another mask.

## Public arguments and options

- `--center/-c` (optional, default: `"0.5,0.5"`) — Center X,Y
- `--width/-w` (optional, default: `0.5`) — Width
- `--height` (optional, default: `0.5`) — Height
- `--softness/-s` (optional, default: `0.0`) — Soft edge

## Boundaries and gotchas

- `--center` must contain exactly two comma-separated floats.
- Dry-run is genuinely non-mutating for this command.
- The success response only contains the generated node name.
- There is no CLI range validation for center, width, height, or softness.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion mask rectangle --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
