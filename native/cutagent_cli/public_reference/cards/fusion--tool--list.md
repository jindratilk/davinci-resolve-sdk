# `fusion tool list`

Syntax: `cutagent fusion tool list [--selected]`

## Search terms

- list Fusion tools
- inspect Fusion node graph
- selected Fusion tools
- Fusion tool name type
- find TextPlus node
- verify node cleanup
- Fusion tool IDs unstable
- active composition inventory

## What it does

List Fusion nodes.

## Do not use when

Do not treat numeric `id` as a durable identifier.
Do not infer graph connections or processing order from list order. The output has no upstream/downstream information.
Do not assume `--selected` means exactly one active tool.
Do not use a bare type as a safe mutation target when multiple nodes share that type. Use the exact unique name and verify it.
Do not execute against an ambiguous composition. There is no clip, track, timeline-item, or comp-index selector.

## Preflight and readback

Before any Fusion mutation, record the full list and the `--selected` subset, plus active-tool and graph topology.
After add/paste/keyframe operations, diff the full list to find every new node, including automatically created Merge or BezierSpline helpers.
After deletion/cleanup, require all temporary names and related helpers to be absent, but also verify original connections and pixel output; tool-count equality is not graph equality.
For selection-sensitive commands, compare `--selected` with `fusion tool active` before and after, then restore the original active node.

## Public arguments and options

- `--selected` (optional, default: `false`) — Show only selected tools

## Boundaries and gotchas

- `--selected` is the only command-specific option.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion tool list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
