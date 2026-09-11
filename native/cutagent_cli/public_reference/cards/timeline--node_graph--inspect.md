# `timeline node-graph inspect`

Syntax: `cutagent timeline node-graph inspect`

## Search terms

- inspect timeline node graph
- timeline color graph
- timeline-level nodes
- node graph availability
- DaVinci Resolve graph proxy
- inspect timeline grading graph

## What it does

Inspect the current timeline node graph when available.

## Do not use when

Do not use this command to inspect the current clip's Color page nodes, a Fusion composition, group pre/post-clip graphs, node labels, LUTs, tools, cache state, or graph connections. Choose the corresponding color/Fusion graph command instead.
Do not parse or persist the returned `graph` text as a stable graph contract. Foreign DaVinci Resolve objects are stringified for machine output and are not round-trippable.

## Preflight and readback

Before execution, activate the exact timeline and distinguish timeline-level graph state from clip/group/Fusion node state.
Use a graph-specific structured command for node details and independently verify the intended timeline/color state in DaVinci Resolve.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- There is no `--timeline` option; activate another timeline separately.
- The command does not enumerate nodes, indexes, names, labels, tools, LUTs, keyframes, connections, versions, cache modes, grades, or graph type.
- It does not prove that the graph belongs to a particular clip or group.
- It does not compare the graph with UI state or render output.
- It does not return the current timeline name, project name, timeline id, or graph id.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent timeline node-graph inspect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
