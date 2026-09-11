# `color grade-apply`

Syntax: `cutagent color grade-apply PATH [--clip VALUE] [--mode VALUE] [--require-render-proof]`

## Search terms

- apply DRX grade to clip
- import color grade file
- restore saved DaVinci Resolve look
- paste DRX onto timeline item
- apply grade with keyframe alignment
- transfer gallery still grade from file
- load node grade onto shot

## What it does

Apply a grade from a grade file.

## Do not use when

Use `color lut` for a baked LUT rather than an editable DRX node grade. Do not use mode 0 when the DRX contains keyframed corrections that must align by source timecode/start frame; choose mode 1 or 2 deliberately after inspecting source and target timing.

## Preflight and readback

Before applying, verify the DRX is a real file, preserve the target’s current grade as a named version/DRX, inspect node count and keyframes, and dry-run with the intended mode.

## Public arguments and options

- `PATH` (required) — DRX file path
- `--clip` (optional)
- `--mode` (optional, default: `0`) — Grade mode: 0=No keyframes, 1=Source TC aligned, 2=Start Frames aligned
- `--require-render-proof/--setup-only` (optional, default: `true`) — Export before/after Color Page frames or use exact grade readback only

## Boundaries and gotchas

- Only modes 0, 1, and 2 are accepted.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color grade-apply --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
