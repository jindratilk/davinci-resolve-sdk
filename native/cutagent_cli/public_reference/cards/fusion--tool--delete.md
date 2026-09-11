# `fusion tool delete`

Syntax: `cutagent fusion tool delete TOOL_NAME [--force]`

## Search terms

- delete Fusion tool
- remove Fusion node
- force delete Fusion tool
- confirmation required tool deletion
- verify deleted Fusion tool
- delete orphan Background
- clean up Fusion graph
- tool delete false positive

## What it does

Delete a Fusion node.

## Do not use when

Do not delete a guessed name or broad type alias. List tools and identify the exact unique target first.
Inventory and clean them individually.
Do not execute against an ambiguous active composition. There is no clip, track, timeline-item, or comp-index selector.
Do not use delete as undo for paste/add without first restoring the original output path and active tool; selection-dependent helpers may exist.

## Preflight and readback

Before execution, verify the exact active composition and run tool list, attrs, inputs, outputs, graph export, active-tool readback, and a representative frame where relevant.
Dry-run the exact target.
After forced deletion, list tools and require the exact name to be absent.
When cleaning a temporary/pasted graph, restore original connections and active selection first, then delete every discovered new node by exact name and verify the final baseline.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name to delete
- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- `--force` and `-f` skip confirmation.
- Dry-run/forced success recoverability metadata was `retryable`; missing force was `manual`.
- Structured dry-run did not remove it.

## Stable public error codes

- `API_CALL_FAILED`
- `CONFIRMATION_REQUIRED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion tool delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
