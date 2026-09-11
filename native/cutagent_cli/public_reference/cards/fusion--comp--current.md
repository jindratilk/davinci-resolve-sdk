# `fusion comp current`

Syntax: `cutagent fusion comp current`

## Search terms

- show current Fusion composition
- inspect active Fusion comp
- get Fusion comp frame range
- current composition info
- identify active Fusion graph
- show comp global range
- which Fusion comp is active
- inspect composition name
- current clip first Fusion comp
- check whether a Fusion comp is open

## What it does

Read the current Fusion composition.

## Do not use when

Use `clip fusion list --track N --record-frame REF` when the question is how many compositions are attached to a specific clip or which comp indices/names exist. `fusion comp current` can return only one implicitly resolved comp.
Current reports no tools.
It inspects graph nodes rather than comp range metadata.
Use `timeline current-item`, `timeline track items`, or a track/frame selector when the timeline clip identity matters. A global Fusion-current comp can take precedence over the clip under the current playhead.
Use `fusion comp range`, `rename`, `play`, `stop`, `render`, or `delete` for the corresponding mutation. This command is read-only.

## Preflight and readback

Before reading, identify the intended timeline and put the playhead inside the target video item, not exactly at its exclusive end. Verify the clip's composition list when there can be multiple comps.
If `fusion comp current` reports no active composition but `clip fusion list` shows one, move the playhead inside that clip and retry.
Before any subsequent mutation, explicitly re-establish the intended comp and clip. Current state can change when the user switches timeline, moves the playhead, selects another clip, opens a different comp tab, or another command changes page/context.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- There is no `--clip`, `--track`, `--record-frame`, or `--comp` option.
- Do not parse or compare that field without type-checking.
- Missing attributes silently produce omitted range keys or an empty name.
- Do not infer route support from those metadata fields alone.
- The command does not itself branch on Studio/Free or report edition compatibility.
- It does not lock the composition during read.
- The values can become stale immediately if playback, rendering, range edits, or UI context changes concurrently.

## DaVinci Resolve editions

The command does not itself branch on Studio/Free or report edition compatibility. - It does not lock the composition during read.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fusion comp current --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
