# `fusion node connect`

Syntax: `cutagent fusion node connect SRC_TOOL SRC_OUTPUT DST_TOOL DST_INPUT`

## Search terms

- connect Fusion nodes
- Fusion output to input
- ConnectTo Fusion
- replace MediaOut input
- inspect Fusion endpoints
- Fusion connect false positive

## What it does

Connect Fusion nodes.

## Do not use when

Do not connect guessed endpoint names.
Do not use this against an ambiguous active composition. The command provides no clip, track, timeline-item, or comp-index selector.
Do not assume connecting to an already occupied input preserves its previous source.
Do not trust `connected:true` as readback.
Do not use this as a transactional graph rewrite.
Do not leave a diagnostic node in the output path.

## Preflight and readback

Before execution, identify the exact current composition and list tools.
Dry-run the exact endpoints and confirm that the frame or graph remains unchanged. Dry-run does not resolve tools or endpoints, so it cannot prove the names exist.
For temporary tests, restore the recorded original source with another explicit connect, export the same frame, and compare against baseline. Finally list tools and remove only uniquely named temporary nodes.

## Public arguments and options

- `SRC_TOOL` (required) — Source tool/node name
- `SRC_OUTPUT` (required) — Source output name (e.g., Output)
- `DST_TOOL` (required) — Destination tool/node name
- `DST_INPUT` (required) — Destination input name (e.g., Input, Foreground, Background)

## Boundaries and gotchas

- Dry-run returns only a message and does not connect to DaVinci Resolve.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion node connect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
