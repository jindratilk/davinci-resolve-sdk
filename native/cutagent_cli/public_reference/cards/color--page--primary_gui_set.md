# `color page primary-gui-set`

Syntax: `cutagent color page primary-gui-set [CLIP_NAME] [--track VALUE] [--at VALUE] [--temperature VALUE] [--tint VALUE] [--contrast VALUE] [--pivot VALUE] [--mid-detail VALUE] [--color-boost VALUE] [--shadows VALUE] [--highlights VALUE] [--saturation VALUE] [--hue VALUE] [--lum-mix VALUE] [--require-render-proof]`

## Search terms

- set Color page primaries in GUI
- adjust selected node temperature and tint
- change contrast and pivot visibly
- set saturation on current Color node
- type Color Wheels numeric values
- adjust midtone detail and color boost
- change highlights and shadows on selected node
- set hue or luminance mix through DaVinci Resolve UI
- GUI primary correction

## What it does

Set selected-node Primaries controls through the custom edit-owned interface.

## Preflight and readback

Before running, identify the exact timeline and clip, move to the intended Color node, and record the selected-node identity or a screenshot; with a named clip, expect the command to reposition the playhead. Verify macOS Accessibility and Screen Recording permission and keep DaVinci Resolve unobscured with an ordinary main window available. Capture a reference frame and decide whether the requested values should visibly change that frame. Reconfirm the selected node and numeric fields in the Color Wheels palette, inspect the frame for the intended tonal/color change, and restore the original page/playhead manually if workflow continuity requires it.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--track` (optional) — Exact 1-based video track selector
- `--at` (optional) — Exact timeline position selector
- `--temperature/--temp` (optional) — Selected-node Primaries Temp GUI value
- `--tint` (optional) — Selected-node Primaries Tint GUI value
- `--contrast` (optional) — Selected-node Primaries Contrast GUI value
- `--pivot` (optional) — Selected-node Primaries Pivot GUI value
- `--mid-detail` (optional) — Selected-node Primaries Mid/Detail GUI value
- `--color-boost` (optional) — Selected-node Primaries Color Boost GUI value
- `--shadows` (optional) — Selected-node Primaries Shadows GUI value
- `--highlights` (optional) — Selected-node Primaries Highlights GUI value
- `--saturation/--sat` (optional) — Selected-node Primaries Saturation GUI value
- `--hue` (optional) — Selected-node Primaries Hue GUI value
- `--lum-mix` (optional) — Selected-node Primaries Lum Mix GUI value
- `--require-render-proof/--setup-only` (optional, default: `true`) — Require before/after rendered-frame pixel proof. Use --setup-only only inside a larger workflow that will perform final render proof.

## Boundaries and gotchas

- At least one control is required.
- `--setup-only` returns setup-only/pending-manual verification even after successful typing.
- It deliberately does not claim a finished grade.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page primary-gui-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
