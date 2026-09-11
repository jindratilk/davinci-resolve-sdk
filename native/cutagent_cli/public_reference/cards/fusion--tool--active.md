# `fusion tool active`

Syntax: `cutagent fusion tool active [TOOL_NAME]`

## Search terms

- active Fusion tool
- current Fusion tool
- set ActiveTool
- COMPS ActiveTool
- Fusion flow selection
- verify selected node
- restore Fusion active tool
- active tool dry-run

## What it does

Check the active Fusion node.

## Do not use when

Do not use active selection as a durable tool identifier. User interaction, page changes, node creation/deletion, and other Fusion operations can change selection.
Do not assume the currently active tool is connected to MediaOut or relevant to the desired clip result. Inspect graph topology independently.
Do not set selection in an ambiguous composition. The command has no clip, track, timeline-item, or comp-index selector.
Do not treat the setter message as readback.
Do not use it as a substitute for explicit `--tool` arguments in later commands. Selection-dependent behavior is fragile and not encoded into an execution plan.
Do not forget to restore the prior active tool after tests; selection can influence DaVinci Resolve auto-connect behavior for newly added nodes.

## Preflight and readback

Remember that dry-run does not prove the tool exists.
Observe the Fusion flow when UI state matters.
If the original state was `(none)`, note that this command exposes no clear-selection operation.

## Public arguments and options

- `TOOL_NAME` (optional) — Tool name to activate (omit to show current)

## Boundaries and gotchas

- Changing active tool does not alter graph connections or media by itself, but it can affect subsequent selection-sensitive auto-connect behavior.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion tool active --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
