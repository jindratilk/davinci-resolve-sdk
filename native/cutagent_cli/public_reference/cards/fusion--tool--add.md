# `fusion tool add`

Syntax: `cutagent fusion tool add TOOL_TYPE [--name VALUE] [--x VALUE] [--y VALUE]`

## Search terms

- add Fusion tool
- create TextPlus tool
- name Fusion tool
- Fusion flow coordinates
- orphan Background tool
- verify new Fusion tool
- unsupported Fusion registration
- clean up temporary Fusion tool

## What it does

Add a Fusion node.

## Do not use when

Do not use a guessed registration ID. Available built-in, Fuse, and plugin tool types depend on the installed DaVinci Resolve/Fusion environment.
Do not assume a created tool is connected. It can be orphaned, or DaVinci Resolve can auto-connect it according to current flow selection.
List tools and use the actual returned/discovered name.
Do not execute against an ambiguous active composition. There is no clip, track, timeline-item, or comp-index selector.
Do not leave temporary tools behind. Use a globally unique name, preserve the graph and active selection, and delete only that exact tool after readback.

## Preflight and readback

Before execution, verify the project, timeline item, active composition, tool list, active tool, and graph topology.
Use a unique requested name and dry-run the exact type/coordinates.

## Public arguments and options

- `TOOL_TYPE` (required) — Tool type (TextPlus, Merge, Background, etc.)
- `--name` (optional) — Custom tool name
- `--x` (optional, default: `-32768`) — X position (-32768 = auto)
- `--y` (optional, default: `-32768`) — Y position (-32768 = auto)

## Boundaries and gotchas

- Options are `--name TEXT`, `--x INTEGER`, and `--y INTEGER`.
- Unlike `fusion node add`, tool-add dry-run returns structured action/type/name/coordinate/route fields.

## Stable public error codes

- `MISSING_ARGUMENT`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion tool add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
