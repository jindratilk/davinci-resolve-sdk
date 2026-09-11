# `clip take add`

Syntax: `cutagent clip take add MEDIA_NAME [--clip VALUE] [--start-frame VALUE] [--end-frame VALUE]`

## Search terms

- add alternate take to clip
- put another source in take stack
- replace shot with optional alternate
- add Media Pool clip as take
- create take selector choices
- audition alternate performance
- add alternate source range
- build DaVinci Resolve take stack

## What it does

Add a media pool clip as a take on a timeline clip.

## Do not use when

Use multicam for synchronized camera angles and compound clips for grouping edits. Do not use takes as a substitute for aligning sources: this command accepts source frames but performs no waveform/timecode sync.

## Preflight and readback

List the target's current stack and verify the candidate Media Pool clip, fps, duration, audio layout, and desired source frame range. Add with explicit start/end when deterministic trimming matters. Immediately list takes again and confirm count increased, original/new ordering, selected index, media name, and returned range. Render or inspect the selected alternative only after explicitly selecting it.

## Public arguments and options

- `MEDIA_NAME` (required) — Media Pool clip to add as a take
- `--clip` (optional) — Timeline clip name (current clip when omitted)
- `--start-frame` (optional) — Source start frame for the take
- `--end-frame` (optional) — Source end frame for the take

## Boundaries and gotchas

- Global `--dry-run` is broken and mutating.
- `--end-frame` without `--start-frame` is rejected.
- The command does not expose fps conversion.

## Examples

- `cutagent clip take add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
