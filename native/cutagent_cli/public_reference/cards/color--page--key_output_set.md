# `color page key-output-set`

Syntax: `cutagent color page key-output-set [CLIP_NAME] --gain VALUE`

## Search terms

- set node Key Output Gain
- fade Color node
- reduce grade strength
- node output opacity
- mix corrected image with original
- attenuate first Color correction
- key tab output gain
- make grade subtler

## What it does

Set Color Page Key Output Gain using project.

## Do not use when

Use `layer-mixer-set --opacity` to attenuate a specific branch feeding a Layer Mixer, `bleach-bypass-intensity-set` for the complete fixed bleach-bypass workflow, and Edit-page clip opacity/composite commands for timeline compositing. Use node enable/disable for an on/off bypass.

## Preflight and readback

Reinspect other nodes to ensure the generic first-container placement did not attenuate the wrong correction.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--gain/--output-gain` (required) — Key Output Gain value, 0..1

## Boundaries and gotchas

- No `--node` option exists.
- Gain 1 can still write/retain explicit Key Output metadata rather than removing it; use param deletion only when removal of the encoded parameter is specifically required and supported.

## Examples

- `cutagent color page key-output-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
