# `edit split`

Syntax: `cutagent edit split [--at VALUE] [--track-type VALUE] [--track VALUE] [--batch VALUE] [--input VALUE] [--batch-json VALUE] [--allow-partial] [--respect-locks]`

## Search terms

- split clip at playhead
- legacy split command
- cut timeline clip
- blade video and audio
- razor clip at timecode
- divide item into two segments
- add edit point
- split all tracks at frame
- batch split timeline clips
- compatibility alias for blade
- cut clip without ripple
- split track 1 item

## What it does

Add blade cuts at the playhead.

## Do not use when

Use `edit delete-through-edit` to heal a redundant existing edit, trim for moving one edge, ripple-delete for removing material/closing time, or a marker when no real cut is wanted.
Do not use this on cloud/PostgreSQL, unsaved/default or ambiguous project databases, nonordinary timeline objects, or without post-reopen DaVinci Resolve proof. Do not interpret “split” as splitting a Media Pool source, creating a compound clip, detaching audio or dividing files on disk.

## Preflight and readback

Require every cut to be strictly inside the intended item and review absolute record frames/target ids.
Afterward, require the intended project/timeline—not `Untitled Project`—to reopen. Independently list every touched track and prove exact record/source continuity, expected item-count increase, links, names, markers, effects, retimes and rendered/audio continuity across each new boundary.

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

- Dry-run connects and performs real read-only target/lock/time preflight.
- A cut must be strictly interior.
- `--track-type all` can target both video and audio, and `--track 0` means every matching track.
- `--respect-locks` is default.
- `--ignore-locks` deliberately bypasses that preflight protection; it does not unlock tracks.
- `--batch`, `--input` and `--batch-json` are alternate sources and mutually exclusive under the shared loader.
- Without `--allow-partial`, any preflight error aborts the whole batch.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent edit split --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
