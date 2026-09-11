# `color export-lut`

Syntax: `cutagent color export-lut OUTPUT_PATH [--clip VALUE] [--type VALUE]`

## Search terms

- export clip grade as LUT
- bake color grade to cube
- create LUT from current Color page look
- export 17 point or 33 point LUT
- save DaVinci Resolve grade as .cube
- turn node grade into LUT
- deliver look LUT from timeline clip

## What it does

Export current clip grade as LUT from Color page context.

## Do not use when

Use `color curves` or `color huesat` to create a mathematical LUT without an existing clip grade, gallery still export for a DRX that preserves editable grade structure, and `color grade-apply` to transfer that DRX. Use a render or DRX/project interchange for those looks.

## Preflight and readback

Back up an existing destination manually.

## Public arguments and options

- `OUTPUT_PATH` (required) — Output LUT path
- `--clip` (optional) — Clip name (current clip when omitted)
- `--type` (optional, default: `2`)

## Boundaries and gotchas

- `--type` has no CLI enum validation.
- Do not infer an untested type mapping from the integer alone.
- A LUT bakes only representable pixel transforms.
- Window geometry, node topology, keyframes, tracking, source-specific transforms, and many OpenFX cannot be reconstructed from it.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent color export-lut --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
