# `clip fusion tool-get`

Syntax: `cutagent clip fusion tool-get TOOL_NAME INPUT_NAME [--comp VALUE] [--clip VALUE] [--track VALUE] [--record-frame VALUE]`

## Search terms

- get TextPlus StyledText
- inspect Fusion parameter value
- verify tool-set result
- query node control by name
- check Fusion Inspector input

## What it does

Read a Fusion node value.

## Do not use when

Do not interpret null as proof that a real input's value is null: misspelled/nonexistent input names also return null successfully.

## Preflight and readback

For verification after tool-set, compare the returned type/value to the intended value and also inspect/render the affected frame. No cleanup is needed for this read, but retain a pre-value before any subsequent setter so it can be restored.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name (e.g., TextPlus1)
- `INPUT_NAME` (required) — Input name (e.g., StyledText)
- `--comp` (optional, default: `1`) — Composition index
- `--clip` (optional)
- `--track` (optional) — Video track index selector
- `--record-frame/--at` (optional) — Record-domain frame/time selector

## Boundaries and gotchas

- Animated input readback can represent only Fusion's current evaluation context, which the command does not report or set.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent clip fusion tool-get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
