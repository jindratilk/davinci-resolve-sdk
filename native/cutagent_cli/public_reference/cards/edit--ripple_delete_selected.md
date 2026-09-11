# `edit ripple-delete-selected`

Syntax: `cutagent edit ripple-delete-selected [--clip VALUE] [--at VALUE] [--track-type VALUE]`

## Search terms

- ripple delete one timeline clip
- remove selected clip and close gap
- delete item under playhead with ripple
- remove linked video and audio clip
- close gap after deleting shot
- delete named clip and shift later items
- remove audio item with ripple
- ripple current video item
- lift and close gap for one clip
- remove resolved item without EDL round trip

## What it does

Remove the selected clip and closed the gap.

## Do not use when

Use `edit ripple-delete` only when an arbitrary time interval must be rewritten through an EDL into a separate timeline. Use `edit remove` for a non-ripple one-item lift, `edit remove-range` for broad whole-item non-ripple deletion, or trim/blade commands for only part of an item.
Mismatched linked spans, overlapping protected items, stale snapshots, or ambiguous targets are rejected before writing. The supported item-level linked A/V slice has real-media DaVinci Resolve proof; broader roll/range behavior remains partial.

## Preflight and readback

Before mutation, run the exact command with `--dry-run` and inspect every selected reference. List downstream items on all affected video/audio tracks, measure expected shift from the selected duration(s), verify true link relationships and check locks. Checkpoint the timeline. Prefer explicit `--clip` only when unique across all tracks, or explicit `--at` only when exactly one item of the requested type covers that position.
Afterward, list each selected track and linked counterpart track. Prove the original item(s) are absent, the gap closed by the expected frame count, downstream source/record ranges remain correct, other tracks stayed synchronized and the timeline duration changed as intended.

## Public arguments and options

- `--clip` (optional) — Target clip name; defaults to the current video clip
- `--at` (optional) — Record-domain frame/timecode inside the target item
- `--track-type` (optional, default: `"linked"`) — Selection scope: linked, video, or audio

## Boundaries and gotchas

- The command deletes whole resolved TimelineItems only.
- It cannot ripple-delete an arbitrary subrange without first splitting at both boundaries.
- `--track-type` accepts exactly `linked`, `video` or `audio`; default is `linked`.
- A name found on multiple tracks or an `--at` covered by stacked items is rejected as ambiguous rather than choosing a layer.
- Name matching is case-insensitive across timeline name, Media Pool name, file path and basename aliases.
- For video/linked selection, supplying `--clip` takes precedence and `--at` is ignored for disambiguation.
- Duplicate named video items remain ambiguous even when `--at` points inside one.
- Audio selection does use `--at` to filter named audio matches first.
- A video-only ripple can desynchronize audio or other tracks.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent edit ripple-delete-selected --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
