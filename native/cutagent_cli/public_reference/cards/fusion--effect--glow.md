# `fusion effect glow`

Syntax: `cutagent fusion effect glow [--intensity VALUE]`

## Search terms

- add glow to Fusion composition
- create SoftGlow node
- luminous halo around edges
- glow current Fusion comp output
- add inline Fusion glow effect
- make highlights bloom
- diffuse bright graphics
- soften light with glow
- add full-frame SoftGlow
- increase Fusion glow gain
- stack glow effects
- bloom MediaIn before MediaOut

## What it does

Add a soft glow effect inline.

## Do not use when

Use `color page ofx-glow-set` when glow belongs to the clip's Color-page finishing pipeline.
Re-running this high-level command creates another node and can compound the look.
This command creates no mask and processes the entire connected image stream.
Use `fusion effect blur` for general spatial softening without the characteristic luminous halo, or `fusion effect sharpen` when the request is to increase edge contrast rather than bloom highlights.
Do not use this command as a non-mutating preview.
Do not run against an ambiguous active comp. Position the clip/page/playhead deliberately and confirm with `fusion comp current` and graph readback; the command has no clip, comp-index, or tool selector.

## Preflight and readback

Before adding glow, verify the active project, timeline, clip, and composition. Run `fusion comp current` and `fusion tool list`, then export the comp when exact topology matters.
Check whether a SoftGlow already exists and whether the user intends to edit it or stack another. Inspect masks, branched image paths, multiple MediaOut nodes, and Fusion's selected tool because DaVinci Resolve can auto-connect a newly added tool before the wrapper attempts its own routing.
Treat both dry-run and failure as potentially mutating.
Export the same timeline frame and compare it to baseline; a node's existence and parameter value do not prove that pixels pass through it.
If the node was orphaned, inserted into the wrong branch, or stacked unintentionally, explicitly delete it and reconnect the intended source to MediaOut, or restore a saved composition. This command has no undo, cleanup, checkpoint, or graph restoration.

## Public arguments and options

- `--intensity/-i` (optional, default: `0.5`) — Glow intensity

## Boundaries and gotchas

- Global `--dry-run` is mutating.
- Only the first MediaIn and first MediaOut found are considered.
- There is no input range validation.
- Only Gain is changed.
- Results depend on DaVinci Resolve's existing/default SoftGlow settings, which the command does not return or verify.
- No time, keyframe, frame range, or animation option exists.
- The command does not switch pages, restore UI selection, preserve the selected node, checkpoint the comp, render a verification frame, or roll back after errors.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion effect glow --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
