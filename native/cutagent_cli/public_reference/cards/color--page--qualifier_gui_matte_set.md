# `color page qualifier-gui-matte-set`

Syntax: `cutagent color page qualifier-gui-matte-set [CLIP_NAME] [--softness VALUE] [--blur VALUE] [--clean-black VALUE] [--clean-white VALUE] [--denoise VALUE] [--grow-shrink VALUE] [--require-render-proof]`

## Search terms

- refine qualifier matte in GUI
- clean black in HSL key
- clean white in qualifier
- blur qualifier edges
- denoise keyed matte
- grow or shrink qualifier matte
- soften Color page key
- improve noisy qualifier selection
- proof-gated matte finesse
- adjust current node qualifier refinement

## What it does

Set Color Page Qualifier matte and refinement controls through a proof-gated interface.

## Do not use when

Use `qualifier-gui-hsl-set` to establish/change HSL threshold ranges. Use Magic Mask refinement commands for neural object/person masks, and Power Window feather controls for geometric windows. Do not expect default render proof to succeed on a qualifier node with no visible correction.

## Preflight and readback

Put a visible, reversible correction on that node if final pixel proof is required and preserve playhead state when targeting a named clip. Confirm rendered-proof locality and undo/restore manually if only part of the requested controls landed.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--softness` (optional)
- `--blur` (optional)
- `--clean-black` (optional)
- `--clean-white` (optional)
- `--denoise` (optional)
- `--grow-shrink` (optional)
- `--require-render-proof/--setup-only` (optional, default: `true`) — Require before/after rendered-frame pixel proof. Use --setup-only only inside a larger workflow that will apply a visible correction and perform final render proof.

## Boundaries and gotchas

- The scalar normalizer does not check finiteness.
- The inferred numeric plan must be inspected to ensure it did not target a channel-specific soft control unexpectedly.
- Default frame-difference proof observes only final pixels.
- A refinement can change a matte without changing pixels if no grade is localized by it; conversely, a pixel change does not prove matte cleanliness.
- `--setup-only` returns pending-manual/setup-only state and explicitly is not final-grade success.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page qualifier-gui-matte-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
