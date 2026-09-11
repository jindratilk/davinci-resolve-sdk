# `clip composite`

Syntax: `cutagent clip composite [NAME] [--mode VALUE] [--opacity VALUE]`

## Search terms

- set clip opacity
- change timeline clip blend mode
- multiply one video clip over another
- make overlay semi-transparent
- screen blend timeline clip
- adjust video occurrence transparency
- set DaVinci Resolve composite mode

## What it does

Check clip composite settings.

## Do not use when

Use `clip transform` when opacity is part of a larger transform/crop change and a single transform operation is easier to verify. Use Fusion Merge/compositing controls for node-based layer operations, masks, animated blends, or blend behavior inside a Fusion composition. Use Color-page key/matte controls for grading opacity.

## Preflight and readback

Confirm there is meaningful content below the target if a blend mode is being evaluated, and save the numeric mode/opacity getter output. After an opacity write, re-run the getter and inspect/render an overlap frame.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--mode` (optional) — Composite mode
- `--opacity` (optional) — Opacity 0-100

## Boundaries and gotchas

- Opacity changes only this resolved visual timeline item.
- It does not lower linked audio, change track opacity globally, or add opacity keyframes.
- Duplicate names have no track/time disambiguation.

## Examples

- `cutagent clip composite --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
