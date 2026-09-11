# `fusion effect blur`

Syntax: `cutagent fusion effect blur [--strength VALUE]`

## Search terms

- blur Fusion composition
- soften Fusion image
- add Gaussian blur node
- blur current comp output
- make Fusion clip blurry
- soften sharp edges in Fusion
- add inline Blur tool
- defocus Fusion graphic
- obscure image with blur
- blur entire Fusion frame
- reduce detail in Fusion comp
- add fast Gaussian blur

## What it does

Add a blur effect inline.

## Do not use when

Use `color page softening-set` when the requested softening belongs to the Color-page grading/finishing pipeline rather than a Fusion node graph. It has different targeting, processing order, and verification.
Re-running this high-level command creates another Blur and compounds processing.
Use `fusion effect sharpen` to increase local edge contrast, `fusion effect glow` for luminous diffusion, or a purpose-specific defocus/motion/directional blur tool when ordinary symmetric Blur is not the intended look.
This command affects the whole connected image stream.
Do not run against an ambiguous active comp. Use clip/page/playhead positioning and `fusion comp current`/clip-scoped graph readback first; the command has no clip, comp-index, or tool selector.

## Preflight and readback

Before adding Blur, verify the active project, timeline, clip, and comp. Run `fusion comp current`, `fusion tool list`, and preferably export the composition so the exact MediaIn-to-MediaOut chain is known. Capture a representative unblurred frame when visible proof matters.
Check for an existing Blur and decide whether to edit it or intentionally stack another.
Do not use global `--dry-run` as a safety preview.
Export the same representative timeline frame and compare it with baseline; graph presence alone does not prove that pixels pass through the node.
If the wrong node was inserted, use an explicit tool-delete/reconnect workflow or restore the saved comp. The command itself provides no undo or cleanup.

## Public arguments and options

- `--strength/-s` (optional, default: `5.0`) — Blur strength

## Boundaries and gotchas

- Global `--dry-run` is fully mutating.
- Only the first MediaIn and first MediaOut found are considered.
- There is no input range validation.
- Do not translate a user-specified pixel radius directly.
- No frame, range, keyframe, or time option exists.
- It does not switch pages, restore prior UI selection, preserve a selected node, checkpoint the comp, or render a verification frame.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion effect blur --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
