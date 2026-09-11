# `color page qualifier-gui-hsl-set`

Syntax: `cutagent color page qualifier-gui-hsl-set [CLIP_NAME] [--hue VALUE] [--saturation VALUE] [--luma VALUE] [--softness VALUE] [--hue-softness VALUE] [--saturation-softness VALUE] [--luma-softness VALUE] [--require-render-proof]`

## Search terms

- set HSL qualifier range in GUI
- key a color by hue saturation luminance
- isolate a hue range
- set qualifier low high thresholds
- soften HSL key edges
- wrap hue range across red
- edit current node HSL key
- create proof-gated Color qualifier
- type qualifier values through DaVinci Resolve UI

## What it does

Set Color Page Qualifier HSL controls through a proof-gated interface.

## Do not use when

Use `qualifier-gui-matte-set` to refine an existing key with Blur, Clean Black, Clean White, Denoise, Grow/Shrink or generic matte softness. Use `qualifier-sample` first when the correct range should be derived from an image patch rather than guessed. Do not use this command to target node 2 or any numeric node index: it always edits the current selection. Do not end a complete grading workflow with `--setup-only`; a qualifier mask alone often makes no rendered pixel change.

## Preflight and readback

Derive the desired range from a sample/scope, check whether Hue crosses 0°, and preserve the original playhead/page state if a named clip is used. Verify the qualifier matte/highlight and the locality of the actual correction, not merely a global pixel difference; manually restore any unintended partial GUI edits.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--hue` (optional)
- `--saturation` (optional)
- `--luma` (optional)
- `--softness` (optional) — Set Hue/Saturation/Luminance GUI soft controls, 0-1 or 0-100
- `--hue-softness` (optional) — Set Hue Soft only, 0-1 or 0-100
- `--saturation-softness/--sat-softness` (optional) — Set Saturation Low/High Soft, 0-1 or 0-100
- `--luma-softness` (optional) — Set Luminance Low/High Soft, 0-1 or 0-100
- `--require-render-proof/--setup-only` (optional, default: `true`) — Require before/after rendered-frame pixel proof. Use --setup-only only inside a larger workflow that will apply a visible correction and perform final render proof.

## Boundaries and gotchas

- There is no `--node`.
- The clip name can activate a timeline item but does not change the selected Color node, so stale node selection is the main wrong-target risk.
- `--softness` does nothing for a channel whose requested range spans at least 0.98.
- Per-channel softness is also emitted only when that channel's range is present.
- Supplying softness without at least one H/S/L range is rejected; softness does not refine a pre-existing range by itself in this command.
- Missing/ambiguous Accessibility labels abort the write, possibly after earlier controls were changed.
- Default rendered proof can fail when the node has no visible correction, when the mask covers the entire frame, when requested values already match, or when the changed key does not affect the sampled frame.
- A successful pixel difference does not prove correct hue wrap, key locality, matte cleanliness or node identity.
- A mid-sequence GUI failure can leave a partial HSL range; recovery is manual.

## Examples

- `cutagent color page qualifier-gui-hsl-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
