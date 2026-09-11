# `timeline fusion-composition insert`

Syntax: `cutagent timeline fusion-composition insert`

## Search terms

- empty Fusion composition clip
- Fusion composition at playhead
- add blank Fusion clip
- current timeline Fusion generator

## What it does

Insert a Fusion composition into the active timeline.

## Do not use when

Do not use this command to convert existing timeline items into a Fusion clip. Use `timeline fusion-clip create` for that distinct operation.
Do not use it when placement track, duration, name, source inputs, or initial Fusion graph must be specified deterministically. The command exposes no controls for those properties.
Inspect and configure the inserted composition afterward.

## Preflight and readback

Before execution, checkpoint the project; inspect the active timeline, playhead, enabled/target video tracks, track locks, surrounding items, and expected default Fusion Composition duration/placement in the current DaVinci Resolve version.
After execution, re-enumerate the timeline and verify the inserted item's actual track, start/end/duration/name, overlaps, and surrounding structure. Open its Fusion composition to inspect the graph and render/export a proof frame before relying on visual output.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- An active timeline is required.
- Dry-run returns only a generic message.
- The command does not move the playhead.
- It does not provide a name option.
- It does not re-enumerate tracks to prove that exactly one item appeared.
- It does not render or export pixels.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`

## Examples

- `cutagent timeline fusion-composition insert --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
