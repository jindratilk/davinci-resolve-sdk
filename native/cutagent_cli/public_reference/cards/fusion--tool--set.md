# `fusion tool set`

Syntax: `cutagent fusion tool set TOOL_NAME INPUT_NAME VALUE [--time VALUE]`

## Search terms

- set Fusion tool input
- set numeric Fusion value
- set Fusion input at time
- Fusion keyframe false positive
- missing input set success
- verify Fusion input mutation
- restore Fusion tool value

## What it does

Set a Fusion node control.

## Do not use when

Do not use guessed input names.
Do not execute against an ambiguous composition. There is no clip, track, timeline-item, or comp-index selector.

## Preflight and readback

Before execution, establish the intended comp/tool/input using tool list, attrs, and input-ID enumeration. Use focused `fusion tool get` at current and relevant comparison times to capture original values.
Dry-run and inspect parsed value/type and time.
Inspect keyframe list, modifiers/tool list, graph/UI, and rendered output when visually meaningful.
For temporary tests, restore original text/number without `--time` when the original was constant, verify all sampled frames, remove any leaked modifier, and return the complete graph/active selection to baseline.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name
- `INPUT_NAME` (required) — Input name
- `VALUE` (required) — Value to set
- `--time` (optional) — Frame time (creates keyframe if set)

## Boundaries and gotchas

- `--time INTEGER` is the only command-specific option.
- Help describes `--time` as creating a keyframe, but the command does not verify that claim.
- Focused `fusion tool get` can also return success/null for unknown inputs, so endpoint discovery must precede both set and get.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fusion tool set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
