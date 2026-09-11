# `clip current`

Syntax: `cutagent clip current`

## Search terms

- what clip is under the playhead
- identify current timeline item
- inspect clip at cursor
- get active clip details
- find item at current timecode
- current video or audio clip
- show playhead clip duration

## What it does

Check the clip under the playhead.

## Do not use when

Use `clip info NAME` when the target is named and should not depend on playhead position. Use `clip list` when every item on a track is needed, and `clip track-info` when only track identity matters. Use `timeline playhead get` for cursor time itself. Do not use this to identify every item under a stacked playhead; it returns at most one and prioritizes video.

## Preflight and readback

If stacked video/audio items exist, list the relevant tracks first so the one-item priority is understood. After reading, use `clip track-info`, `clip source-range`, or a track list to confirm identity before any mutation; the current result contains no track index or stable item id.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- It does not choose the highest visible layer or return all overlaps.
- A playhead exactly at an item's end does not belong to that item, although `timeline playhead set` may clamp a requested timeline-end frame back to the final item frame.

## Examples

- `cutagent clip current --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
