# `edit blade`

Syntax: `cutagent edit blade [--at VALUE] [--track-type VALUE] [--track VALUE] [--batch VALUE] [--input VALUE] [--batch-json VALUE] [--allow-partial] [--respect-locks]`

## Search terms

- blade clip at playhead
- split timeline clip
- cut video at timecode
- razor all tracks
- split audio clip at frame
- add edit point
- cut linked audio and video
- batch blade timeline
- divide clip into two pieces
- make cuts at multiple positions
- razor track 1
- split clips without ripple

## What it does

Add blade cuts at the playhead.

## Do not use when

Use `edit delete-through-edit` to remove an existing through-edit, `edit ripple-delete-selected` to remove material and close the gap, or trim commands when only a clip edge should move. Do not blade merely to mark a position; use a marker.

## Preflight and readback

Afterward, require the intended project and timeline to reopen—not `Untitled Project`—and independently list every touched track. Verify exact left/right record bounds, source In/out continuity, media identity, link groups, audio effects, retimes, markers, transitions and rendered image/audio across each edit point.

## Public arguments and options

- `--at` (optional) — Timecode/seconds/frames to blade at (default: playhead)
- `--track-type` (optional, default: `"all"`) — Track type: all, video, audio
- `--track` (optional, default: `0`) — Track index (0 = all matching tracks)
- `--batch` (optional) — JSON batch file
- `--input` (optional) — JSON batch file alias
- `--batch-json` (optional)
- `--allow-partial` (optional, default: `false`) — Apply valid entries even when some entries fail preflight
- `--respect-locks/--ignore-locks` (optional, default: `true`) — Respect timeline track locks

## Boundaries and gotchas

- Cut positions must be strictly inside.
- `--track 0` means all matching tracks, not track zero.
- With `--track-type all`, one position may split many overlapping video/audio items.
- If lock readback is unavailable/fails, preflight refuses and suggests `--ignore-locks`; that flag deliberately removes protection rather than unlocking tracks.
- Batch source options `--batch`, `--input` and `--batch-json` are mutually exclusive.
- Without `--allow-partial`, any preflight failure aborts all plans.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent edit blade --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
