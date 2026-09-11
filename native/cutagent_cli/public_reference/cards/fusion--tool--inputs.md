# `fusion tool inputs`

Syntax: `cutagent fusion tool inputs TOOL_NAME`

## Search terms

- list Fusion tool inputs
- MediaIn input names
- MediaOut Input endpoint
- Fusion input values truncated
- prepare Fusion tool set

## What it does

List Fusion node controls.

## Do not use when

Connected and disconnected image inputs can both appear with value `"None"`.
Query a focused input through `fusion tool get` and use owning validators/render evidence.
Do not execute against an ambiguous active composition. There is no clip, track, timeline-item, or comp-index selector.

## Preflight and readback

Before mutation, establish the exact comp/tool with tool list and attrs.
For each relevant ID, run `fusion tool get TOOL ID` at current/target times to obtain focused readback. Preserve exact original values before setting anything.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion tool inputs --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
