# `fusion node delete`

Syntax: `cutagent fusion node delete TOOL_NAME [--force]`

## Search terms

- delete Fusion node
- remove Fusion tool alias
- force delete Fusion node
- Fusion node deletion confirmation
- delete orphan BezierSpline
- verify Fusion tool removal
- clean up Fusion graph
- restore graph after node delete

## What it does

Delete a Fusion node.

## Do not use when

Do not delete a guessed or type-like name. List tools and identify the exact unique node name first.
Do not use this against an ambiguous active composition. It has no clip, track, timeline-item, or comp-index selector.
Do not assume deleting a main tool also removes every related modifier or orphan.
Do not trust `deleted:true` without readback.

## Preflight and readback

Before execution, verify the exact current composition and run `fusion tool list`. Capture the target's type, attributes, inputs, outputs, settings, connections, and any related modifiers.
Dry-run the exact unique name.
After forced deletion, immediately list tools and confirm the exact name is absent. Inspect downstream topology and export/render a representative frame; deleting one node can disconnect or change output.

## Public arguments and options

- `TOOL_NAME` (required) — Tool/node name to delete
- `--force/-f` (optional, default: `false`) — Skip confirmation

## Boundaries and gotchas

- `--force` and `-f` skip confirmation.
- `fusion keyframe clear --force` did not remove those modifier nodes.

## Stable public error codes

- `API_CALL_FAILED`
- `CONFIRMATION_REQUIRED`
- `MISSING_ARGUMENT`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion node delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
