# `fusion tool paste`

Syntax: `cutagent fusion tool paste`

## Search terms

- paste Fusion tools
- Fusion clipboard paste
- comp Paste nodes
- duplicate Fusion tool
- paste auto creates Merge
- selection dependent Fusion paste
- verify pasted tool names
- restore graph after paste
- Fusion paste false positive

## What it does

Paste Fusion nodes.

## Do not use when

Do not assume the clipboard contains only the intended tools or is still populated.
Do not assume a one-tool copy produces one pasted node.
Do not paste while an unintended tool is active.
Do not execute against an ambiguous active composition. There is no clip, track, timeline-item, or comp-index selector.

## Preflight and readback

Before paste, capture the complete tool list, actual graph connections, active tool, and representative output frame. Inventory the expected clipboard content through a controlled prior copy.
Run dry-run and confirm it leaves the graph unchanged.
For cleanup, explicitly restore the original output path before deleting newly created nodes. Restore the prior active tool, delete every discovered pasted/automatic node by exact name, and require final tool-list plus pixel equality.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Name collisions are resolved by DaVinci Resolve; the command does not predict the suffix.
- The suggested tool-list readback finds new names/types but does not reveal actual upstream/downstream connections.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion tool paste --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
