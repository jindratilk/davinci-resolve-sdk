# `fusion tool attrs`

Syntax: `cutagent fusion tool attrs TOOL_NAME`

## Search terms

- Fusion tool attributes
- TOOLS RegID
- Fusion node selected flag
- MediaIn clip attributes
- Fusion image dimensions
- inspect Fusion tool metadata
- Fusion local path exposure
- active composition tool attrs

## What it does

Read Fusion node attributes.

## Do not use when

Do not use attributes as input values.
Do not expose raw output unnecessarily. Media tools can include absolute local paths, media IDs, clip names, and other environment-specific metadata.
Do not use this against an ambiguous active composition. The command has no clip, track, timeline-item, or comp-index selector.
Do not infer graph connectivity from selection/visibility attributes.

## Preflight and readback

Before reading, establish the intended project, timeline item, composition, and exact tool name with `fusion tool list`.
Choose only the keys relevant to the decision.
Compare attributes at the same tool/time/context when diagnosing state changes. Some values such as last-frame/render timing or selected state are transient.
For mutations, capture relevant before/after keys but verify the actual behavior through the owning input, graph, and frame/render readback; attributes alone are supporting evidence.

## Public arguments and options

- `TOOL_NAME` (required) — Tool name

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion tool attrs --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
