# `fairlight clip split`

Syntax: `cutagent fairlight clip split [--at VALUE] [--track VALUE] [--batch VALUE] [--input VALUE] [--batch-json VALUE] [--allow-partial] [--respect-locks]`

## Search terms

- split Fairlight audio clip
- cut audio clip at playhead
- razor audio item
- blade an audio clip
- divide audio clip into two
- split every audio track at timecode
- cut dialogue at a frame
- make an edit point in audio
- separate one audio region into segments
- batch audio blade cuts
- split sound without moving it
- cut audio on one track

## What it does

Split Fairlight audio timeline items through the blade.

## Do not use when

Use `edit blade` when video must be cut, or when an audio/video edit needs a route that explicitly targets both media types. `fairlight clip split` accepts only audio targets and does not split a linked video companion; splitting audio alone can break a synchronized linked edit.
Use `fairlight clip trim` to change an existing head or tail boundary, `fairlight clip slip` to change which source samples play under fixed record boundaries, and `fairlight clip move` or `fairlight clip nudge` to relocate the whole occurrence. Split creates additional timeline item rows while preserving the combined record span.
It targets all eligible items at the chosen point on the chosen track set. Isolate the target, choose a narrower track, or use another item-specific edit route.
Do not use it to preserve clip markers across the new halves.
Do not treat it as a transition-aware audio edit.

## Preflight and readback

Before mutation, run `timeline item-at` at the requested position and immediately to either side, list the relevant audio track(s), inspect locks, links, clip markers, fades/effects, and record/source ranges. Convert the desired location to record-domain frames carefully. For `--track 0`, enumerate every audio track crossing the position because every eligible layer is in scope.
Afterward, query the exact left and right positions with `timeline item-at`. Require the left segment to retain the original start and item ID, the right segment to have a new ID, both durations to meet at the requested frame with no gap/overlap, and the right source In to advance by the left duration. Re-check links, markers and effect/fade behavior, then audition or render across the cut.

## Public arguments and options

- `--at` (optional) — Record-domain timecode/seconds/frames to split at; defaults to playhead
- `--track` (optional, default: `0`) — Audio track index (0 = all matching audio tracks)
- `--batch` (optional) — JSON batch file
- `--input` (optional) — JSON batch file alias
- `--batch-json` (optional)
- `--allow-partial` (optional, default: `false`) — Apply valid entries even when some entries fail preflight
- `--respect-locks/--ignore-locks` (optional, default: `true`) — Respect timeline track locks

## Boundaries and gotchas

- The lifecycle does not explicitly restore the original playhead, clip selection, page, focus or undo history.
- `--at` is record-domain.
- Do not pass a source-frame offset here.
- If `--at` is omitted, the playhead is captured during preflight.
- A modal, timeline switch or playhead change around project close/reopen can invalidate the user's intended cut, so explicit `--at` is safer for unattended work.
- `--track 0` means all audio tracks.
- It can split dialogue, music, effects and layered takes at once; track selection in the UI does not constrain it.
- If lock state cannot be queried, the command fails rather than guessing; `--ignore-locks` is an explicit request to bypass that guard.
- A cut must be strictly inside a clip.
- There is no `--name`, `--item-id`, selection-only, topmost-only or first-match option.
- A clean item-row result does not prove that a crossfade or other edit-boundary object survived correctly.
- Duplicate cuts for the same item at the same frame are rejected.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight clip split --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
