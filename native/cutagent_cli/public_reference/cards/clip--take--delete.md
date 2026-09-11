# `clip take delete`

Syntax: `cutagent clip take delete CLIP INDEX`

## Search terms

- delete alternate take
- remove take 2 from clip
- prune take stack
- discard unwanted alternate source
- remove one DaVinci Resolve take
- clean up clip alternatives
- delete take by index
- keep selected take and remove another

## What it does

Delete a take from a timeline clip.

## Do not use when

Use `clip take finalize` when all alternatives should be discarded and the selected take committed. Do not use delete to remove the timeline item; use clip/timeline edit deletion commands with their ripple semantics.

## Preflight and readback

List takes, identify the exact index/media/range, and note which index is selected. Prefer dry-run first—this specific command's dry-run is safe—and re-list to confirm nothing changed. After real deletion, inspect returned before/after counts and rows, then run list again because indices can shift. Verify the timeline still displays/plays the intended selected source.

## Public arguments and options

- `CLIP` (required) — Clip name
- `INDEX` (required) — Take index

## Boundaries and gotchas

- This is the one take mutator with a working dry-run branch.
- Deleting a take removes only the alternative from this timeline item's stack.
- Duplicate timeline names are first-match, with no track/frame selector.
- A selected-take name change can invalidate the planned target between dry-run and execution.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent clip take delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
