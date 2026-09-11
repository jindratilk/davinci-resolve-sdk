# `fusion node disconnect`

Syntax: `cutagent fusion node disconnect TOOL_NAME INPUT_NAME`

## Search terms

- disconnect Fusion node input
- ConnectTo None Fusion
- detach MediaOut input
- disconnect Merge Foreground
- verify unconnected Fusion input
- restore Fusion graph
- Fusion disconnect false positive
- clear Fusion input source

## What it does

Disconnect a Fusion node input.

## Do not use when

Do not disconnect an input until its current source and the required restoration command are known.
Do not use guessed input names.
Do not use it on an ambiguous composition. It has no clip, track, timeline-item, or comp-index selector.
Do not assume an unconnected image input will preserve the previous image, output transparency, or produce a particular default. Verify actual pixels for the specific tool/input.
Do not trust `disconnected:true` as independent proof. The wrapper ignores the return from `ConnectTo(None)` and performs no topology readback.
Do not use this as a reversible toggle. A second disconnect cannot restore the former source; reconnection requires its exact node and output ID.

## Preflight and readback

Before execution, verify the current project, timeline, clip, and composition. List the destination tool's inputs and capture the existing source with graph export/UI inspection.
Save the exact inverse command, for example `fusion node connect MediaIn1 Output MediaOut1 Input`, before disconnecting. Capture a representative frame if output is expected to change.
Run dry-run first.
Execute the preserved reconnect command in cleanup, even if a later assertion fails. Re-export the same frame and require equality or a justified visual match, then verify the final tool list/topology.

## Public arguments and options

- `TOOL_NAME` (required) — Tool/node name
- `INPUT_NAME` (required) — Input name to disconnect

## Boundaries and gotchas

- Dry-run returns only a message and does not resolve the tool/input.
- There is no `--force` or confirmation even when disconnecting the sole path to MediaOut.
- Final graph cleanup left only the original four tools and the restored MediaIn-to-MediaOut output.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion node disconnect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
