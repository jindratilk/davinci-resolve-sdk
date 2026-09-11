# `fusion tool outputs`

Syntax: `cutagent fusion tool outputs TOOL_NAME`

## Search terms

- list Fusion tool outputs
- Fusion Output endpoint
- connect source output
- MediaIn output ID
- MediaOut output endpoint
- missing tool outputs
- prepare Fusion tool connect

## What it does

List Fusion node outputs.

## Do not use when

Do not assume an exposed output is connected or visibly contributes to MediaOut.
Do not assume every exposed output is semantically appropriate as a connect source.
Do not use output listing as pixel or render-readiness proof. Inspect actual graph connections and render/export representative output.
Do not execute against an ambiguous composition. There is no clip, track, timeline-item, or comp-index selector.

## Preflight and readback

Before connecting tools, establish the intended composition and exact source tool with tool list/attrs, then enumerate its output IDs here.
Pair the chosen source `id` with an independently discovered destination input `id`. Dry-run the exact connect command and preserve existing destination topology.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name

## Boundaries and gotchas

- Endpoint presence does not prove the tool can render successfully.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion tool outputs --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
