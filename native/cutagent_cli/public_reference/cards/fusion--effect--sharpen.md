# `fusion effect sharpen`

Syntax: `cutagent fusion effect sharpen [--amount VALUE]`

## Search terms

- sharpen Fusion composition
- add UnsharpMask node
- increase edge contrast Fusion
- sharpen current comp output
- add inline unsharp mask
- crisp Fusion image
- enhance fine detail
- reduce soft-looking edges
- sharpen MediaIn before MediaOut
- add full-frame sharpening
- Fusion Amount option ignored
- UnsharpMask Gain control

## What it does

Add a sharpen (unsharp mask) effect inline.

## Do not use when

Re-running this command creates another default node and compounds processing.
Use `fusion effect blur` to reduce spatial detail or `fusion effect glow` for luminous diffusion. Sharpening cannot recover genuinely absent focus/detail and can amplify compression blocks, noise, ringing, aliasing, and halos.
This command creates no mask and processes the entire connected image stream.
Do not use global `--dry-run` as a safety preview.
Do not run against an ambiguous active comp. The command has no clip, composition index, tool selector, frame range, or graph-branch option.

## Preflight and readback

Before running, verify the active project, timeline, clip, and composition with `fusion comp current` and `fusion tool list`. Export the composition to establish exact MediaIn-to-MediaOut topology, and capture a representative baseline frame with edges, text, fine detail, or noise.
Inspect existing UnsharpMask nodes and decide whether the request is to edit one or intentionally stack another.
Treat dry-run and failure as potentially mutating.
A null Amount readback is material evidence that the option was ignored, not evidence that the requested value became a default.
Export the same representative frame after mutation and compare it to baseline and to runs with materially different requested amounts.
If a node was orphaned, inserted in the wrong branch, or stacked unintentionally, explicitly delete it and reconnect the intended source to MediaOut, or restore a saved composition. The command provides no undo or cleanup.

## Public arguments and options

- `--amount/-a` (optional, default: `0.5`) — Sharpen amount

## Boundaries and gotchas

- Global `--dry-run` is mutating.
- Only the first MediaIn and first MediaOut found are considered.
- No time, keyframe, frame range, or animation option exists.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion effect sharpen --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
