# `fusion tool get`

Syntax: `cutagent fusion tool get TOOL_NAME [INPUT_NAME] [--time VALUE]`

## Search terms

- get Fusion tool input
- list all Fusion inputs raw
- missing Fusion input null
- MediaIn GlobalIn value
- Fusion input time readback
- all-input numeric key bug
- verify Fusion tool set

## What it does

Read a Fusion node control.

## Do not use when

Do not interpret a focused `null` value as proof that an input exists and is unset. DaVinci Resolve can return null for an unknown input without raising.
Use `fusion tool inputs` for IDs, then focused `fusion tool get TOOL ID`.
Compare multiple frames and inspect animation/modifier/keyframe state independently.
Do not execute against an ambiguous composition. There is no clip, track, timeline-item, or comp-index selector.

## Preflight and readback

Before reading, establish the exact project/timeline item/composition and tool name.
Cross-check focused output with attrs, input enumeration, modifier/keyframe listing, and rendered/UI behavior appropriate to the parameter.
Treat all-input `value` fields as diagnostic best effort.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name
- `INPUT_NAME` (optional) — Input name (omit to show all)
- `--time` (optional) — Frame time (default: current)

## Boundaries and gotchas

- `--time INTEGER` is the only command-specific option.
- There is no dedicated dry-run conditional.
- `--time` accepts negative/out-of-range integers without command-level bounds validation.
- All-input mode ignores `--time`; it always uses current composition time.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion tool get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
