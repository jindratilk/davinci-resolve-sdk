# `fairlight fade-curve`

Syntax: `cutagent fairlight fade-curve --item-id VALUE --direction VALUE [--x VALUE] [--y VALUE] [--linear]`

## Search terms

- audio fade curvature
- fade-in control point
- fade-out control point
- preserve opposite fade

## What it does

Read and edit an audio fade curve without changing either fade duration.

## Do not use when

Do not use for video opacity, arbitrary multi-point gain envelopes, or remote project libraries. Do not invent normalized coordinates or treat unavailable readback as linear.

## Preflight and readback

Inspect the exact clip identity and both fade durations. After editing, verify project and timeline restoration, both curve values, both durations and surrounding effects. Paired 48 kHz PCM renders changed both edge regions while the middle differed by no more than one quantization unit.

## Public arguments and options

- `--item-id` (required) — Exact audio timeline item ID
- `--direction` (required) — in or out
- `--x` (optional)
- `--y` (optional)
- `--linear` (optional, default: `false`) — Reset this fade to a linear envelope

## Boundaries and gotchas

- --x and --y must be supplied together and cannot accompany --linear.
- Resetting one edge does not remove the other edge's point.
- This route preserves existing effect parameters; it does not replace the whole audio effect stack.

## Examples

- `cutagent fairlight fade-curve --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
