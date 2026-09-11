# `color page magic-mask-refine`

Syntax: `cutagent color page magic-mask-refine [CLIP_NAME] [--object-mode VALUE] [--track] [--stroke VALUE]`

## Search terms

- refine Magic Mask
- add Magic Mask stroke
- correct subject selection
- expand Magic Mask selection
- fix missed part of person mask
- refine object matte
- retrack Magic Mask after correction
- add person selection stroke
- improve AI subject mask
- correct Magic Mask edge selection

## What it does

Draw a DaVinci Resolve Color Page Magic Mask refinement stroke.

## Do not use when

Use Power Window detail/transform commands for geometric mask adjustments, or qualifier matte-refine commands for denoise/clean-black/clean-white/blur controls on an HSL key. This command is not a substitute for a minus/exclusion-stroke command—the interface exposes person versus object mode but no positive/negative refinement polarity—and it cannot perform automatic refinement without coordinates.

## Preflight and readback

Confirm macOS GUI permissions and visible-window geometry. Afterward, compare the returned screenshot/export with the pre-refinement image, inspect the matte overlay inside DaVinci Resolve, and, if `--track` was used, scrub the affected range because button-click evidence is not keyframe readback. Preserve a reversible project checkpoint when refining a valuable tracked mask.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--object-mode` (optional, default: `"person"`) — Requested Magic Mask object/refinement mode
- `--track` (optional, default: `false`)
- `--stroke` (optional) — Normalized refinement stroke: x,y;x,y;...

## Boundaries and gotchas

- At least two semicolon-separated `x,y` points are needed, all finite and in the inclusive 0..1 range.
- `--object-mode` accepts `person` or `object` plus aliases (`p`, `people`, `human`, `o`, `obj`).
- It chooses panel mode; it does not express add/subtract polarity or a particular object identity.
- The command does not verify that a prior Magic Mask exists.
- If none exists, the GUI drag may behave like an initial stroke; the returned action label alone does not prove refinement semantics.
- The same macOS-only constraints, fixed-proportion viewer inference, visible active-Space window requirement, open-panel requirement and possible mis-mapped mouse coordinates as `magic-mask-draw-stroke` apply.
- Tracking proof is only that a matching Accessibility control was clicked.
- There is no completion wait or tracked-range validation.
- Required screenshot/export files prove artifact creation, not selection quality.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page magic-mask-refine --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
