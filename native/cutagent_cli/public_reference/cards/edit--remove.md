# `edit remove`

Syntax: `cutagent edit remove --at VALUE [--track-type VALUE] [--track VALUE]`

## Search terms

- delete timeline clip at time
- remove item under playhead position
- clear one clip without ripple
- delete video at frame
- remove audio item at timecode
- lift clip from timeline
- leave gap after deleting clip
- remove one item on V1
- delete timeline item but keep source media
- clear clip at record position
- remove selected track item by time
- non-ripple clip delete

## What it does

Remove the clip at a given position.

## Do not use when

Use Media Pool delete only when the source asset itself—not one timeline instance—must be removed. Use subtitle/marker/transition-specific commands for those object types.
Do not use `--track 0` when several tracks contain an item at the same time; that scope is rejected as ambiguous. Do not assume linked video/audio is handled as a pair because the selected track scope is deliberate.

## Preflight and readback

Before mutation, list the exact track and item covering the requested position, including its start/end, links, locks, transitions, effects and neighbors. Use a positive explicit track index and checkpoint the timeline. Convert timeline-relative versus absolute time carefully, especially on a 01:00:00:00 start.
Afterward, inspect the returned stable target/readback details and, for high-value work, independently list the same track and linked counterpart tracks. Confirm the exact item is absent, neighboring record positions are unchanged and the Media Pool source still exists.

## Public arguments and options

- `--at` (required) — Position of clip to remove
- `--track-type` (optional, default: `"video"`) — Track type: video, audio
- `--track` (optional, default: `0`)

## Boundaries and gotchas

- The command name means one entire TimelineItem, not one frame/range and not source media.
- Only `video` and `audio` are accepted; track types such as subtitle or `all` are rejected before dry-run.
- `--track 0` means search all tracks of the chosen type and succeeds only when exactly one item covers the position; stacked matches are rejected as ambiguous.
- Dry-run returns before connecting or parsing the record reference.

## Examples

- `cutagent edit remove --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
