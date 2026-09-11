# `color mask inspect`

Syntax: `cutagent color mask inspect [--clip VALUE] [--comp VALUE]`

## Search terms

- inspect Fusion mask stack
- list active grading windows
- show qualifier tracker mask chain
- find orphaned color masks
- verify power window attachment
- inspect ColorCorrector EffectMask chain
- troubleshoot clip-attached secondary grade

## What it does

Inspect the active mask chain and orphaned mask.

## Do not use when

Use `color window list` or window-specific getters for geometry, `color qualifier inspect` for qualifier thresholds, tracker inspection for tracking data, and `color graph inspect` for the main image pipe plus all tools.

## Preflight and readback

Preserve the exact mask-chain order and orphan list.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- The output is structural only.
- Only RectangleMask, EllipseMask, PolylineMask, ChromaKeyer, Tracker, ColorCorrector and ChromaticAdaptation participate in the recognized color classification.
- Composition indices are one-based.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color mask inspect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
