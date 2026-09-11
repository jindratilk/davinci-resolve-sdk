# `fusion tool disconnect`

Syntax: `cutagent fusion tool disconnect TOOL_NAME INPUT_NAME`

## Search terms

- disconnect Fusion tool
- ConnectTo None
- remove Fusion input link
- detach MediaOut input
- disconnect Merge Foreground
- verify Fusion disconnection
- restore disconnected Fusion input
- tool disconnect readback
- disconnected Fusion output black

## What it does

Disconnect a Fusion node control.

## Do not use when

Do not disconnect until the current upstream tool/output is known and preserved. The command returns no previous source.
Do not use guessed input names.
Do not execute against an ambiguous active composition. There is no clip, track, timeline-item, or comp-index selector.
Do not trust `Disconnected:` as independent proof.
Do not rely solely on the dry-run-suggested `fusion tool inputs` command.
Do not treat disconnect as reversible by repeating it; restoration requires an explicit source node and output ID.

## Preflight and readback

Before execution, establish the exact composition and destination input, inspect/export the graph, record the upstream source/output, and capture a representative frame.
Prepare the inverse `fusion tool connect SRC OUTPUT DST INPUT` command before disconnecting. Dry-run the exact tool/input and confirm no pixel change.
Understand the destination's behavior with an unconnected input rather than assuming transparency or black.
Run the inverse connect in cleanup and compare the restored frame with baseline. Remove any uniquely named temporary source and confirm the final tool list and active selection.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name
- `INPUT_NAME` (required) — Input name to disconnect

## Boundaries and gotchas

- Dry-run does not connect or validate the tool/input.
- There is no confirmation or `--force`, even for the only MediaOut image input.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion tool disconnect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
