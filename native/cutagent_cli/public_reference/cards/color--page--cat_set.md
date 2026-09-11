# `color page cat-set`

Syntax: `cutagent color page cat-set [CLIP_NAME] [--method VALUE] [--source-illuminant VALUE] [--target-illuminant VALUE]`

## Search terms

- chromatic adaptation transform
- change white point
- D65 to D50 adaptation
- Bradford CAT
- CAT02 transform
- adapt illuminant
- Fusion ChromaticAdaptation
- convert scene white illuminant
- von Kries color adaptation

## What it does

Apply Chromatic Adaptation Transform controls through a Fusion CAT node.

## Do not use when

Use general Fusion effect commands when multiple CAT tools, non-default color-space/gamma controls, blend below 1.0, or an explicit composition index are required; this command exposes none of those choices.

## Preflight and readback

Confirm the clip name is unique on the current timeline.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--method` (optional, default: `"CAT02"`) — Requested CAT method, for example CAT02
- `--source-illuminant` (optional, default: `"D65"`) — Requested source illuminant
- `--target-illuminant` (optional, default: `"D55"`) — Requested target illuminant

## Boundaries and gotchas

- It does not create one CAT per request.
- Do not use this wrapper to preserve a manually customized CAT tool with other working-space settings.
- The command has no `--comp` option and always uses composition 1.

## Examples

- `cutagent color page cat-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
