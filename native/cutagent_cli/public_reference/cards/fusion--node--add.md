# `fusion node add`

Syntax: `cutagent fusion node add TOOL_TYPE [--name VALUE] [--x VALUE] [--y VALUE]`

## Search terms

- add Fusion node
- create Fusion tool alias
- name Fusion node
- position Fusion flow node
- Fusion node x y
- verify created Fusion node
- unsupported Fusion tool type
- remove temporary Fusion node

## What it does

Add a Fusion node.

## Do not use when

Do not use a guessed tool type. Tool registration depends on the installed DaVinci Resolve/Fusion version, Fuses, and plugins; the help examples are not a complete availability guarantee.
Do not treat returned `x` and `y` as coordinate readback.
Independently list tools and inspect the actual node name.
Do not use this when the active composition is ambiguous. There is no clip, track, timeline-item, or composition-index selector.
Do not assume adding a node puts it into the image path. A newly created node can remain orphaned, or DaVinci Resolve may auto-connect it according to current flow selection.
Do not create a temporary node without a cleanup plan. Preserve the exact original graph and delete only the uniquely named test node.

## Preflight and readback

Before execution, verify the current project, timeline, clip, and composition. Capture `fusion tool list`, the relevant output/input IDs, graph topology, and a representative frame when pixels matter.
Use a unique `--name` so later discovery and deletion cannot hit an existing production node.
Check the actual type and actual name rather than the echoed request.
If the node is meant to affect output, connect it explicitly and prove the result with graph plus frame/render readback.

## Public arguments and options

- `TOOL_TYPE` (required) — Tool type (TextPlus, Merge, Background, etc.)
- `--name` (optional) — Custom tool name
- `--x` (optional, default: `-32768`) — X position (-32768 = auto)
- `--y` (optional, default: `-32768`) — Y position (-32768 = auto)

## Boundaries and gotchas

- Command-specific options are `--name TEXT`, `--x INTEGER`, and `--y INTEGER`.
- `--x` and `--y` default to `-32768`.
- The command trims tool type but does not trim or reject an empty custom name.

## Stable public error codes

- `MISSING_ARGUMENT`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion node add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
