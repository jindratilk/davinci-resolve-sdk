# `color page softening-set`

Syntax: `cutagent color page softening-set [CLIP_NAME] [--radius VALUE]`

## Search terms

- soften an entire clip
- add gentle blur finishing pass
- reduce harsh digital detail
- apply isotropic Fusion Blur
- blur video equally horizontal and vertical
- soften skin globally
- make footage less sharp
- add full-frame diffusion blur
- clip-level Fusion softening workaround
- smooth fine detail with Blur

## What it does

Apply a supported Color Page finishing softening pass through the Fusion Blur.

## Do not use when

Use `fusion effect blur` when the active Fusion composition is already the intended target and active-comp targeting is acceptable. Use `clip fusion tool-set` to adjust an existing Blur's X/Y inputs instead of stacking another, and use Fusion masks/merges when only skin, background or another region should soften. Use `color page sharpen-set` for edge enhancement—the two operations are opposites, and placing a full-frame Blur after UnsharpMask can largely cancel its detail work.

## Preflight and readback

Before applying, inspect comp 1 with `clip fusion tools`, locate existing Blur/sharpen/diffusion stages, and decide the required order and whether the effect should be masked. Save the graph and export a detailed reference frame. Compare a full-resolution rendered frame for detail loss, halos, edge handling and unintended text/graphics softness; type-presence verification alone does not prove the requested radius or a useful visual result.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--radius` (optional, default: `2.0`) — Blur radius applied to XBlurSize/YBlurSize, 0..100

## Boundaries and gotchas

- The command cannot create directional blur, anisotropic softening, motion blur, separate axis radii, blend/mix, edge mode, quality or mask inputs.
- Range is 0..100 inclusive.
- On a later failure, graph restoration does not explicitly remove that newly created composition.
- Duplicate filenames can soften the wrong timeline instance.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page softening-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
