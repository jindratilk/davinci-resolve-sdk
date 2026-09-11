# `fusion tool connect`

Syntax: `cutagent fusion tool connect SRC_TOOL SRC_OUTPUT DST_TOOL DST_INPUT`

## Search terms

- connect Fusion tools
- Fusion ConnectTo
- source output destination input
- replace MediaOut source
- restore Fusion graph
- tool connect dry-run

## What it does

Connect Fusion nodes.

## Do not use when

Do not connect guessed endpoint names. List tools, source outputs, and destination inputs first.
Do not assume an occupied destination input will retain its previous source. A new connect can replace the existing link without confirmation.
Do not execute against an ambiguous active composition. There is no clip, track, timeline-item, or comp-index selector.
Do not rely only on `fusion tool inputs` to identify the connected source.

## Preflight and readback

Save the exact inverse connect command and a representative baseline frame.
Remove only uniquely named temporary tools and verify the final graph/tool list.

## Public arguments and options

- `SRC_TOOL` (required) — Source tool name
- `SRC_OUTPUT` (required) — Source output name (e.g., Output)
- `DST_TOOL` (required) — Destination tool name
- `DST_INPUT` (required) — Destination input name (e.g., Input, Foreground, Background)

## Boundaries and gotchas

- There is no `--force` or confirmation for replacing an occupied destination input.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion tool connect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
