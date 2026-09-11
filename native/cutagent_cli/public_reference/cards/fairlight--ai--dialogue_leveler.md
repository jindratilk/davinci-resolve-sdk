# `fairlight ai dialogue-leveler`

Syntax: `cutagent fairlight ai dialogue-leveler [--lifter] [--cleaner] [--gain VALUE] [--clip VALUE]`

## Search terms

- level uneven dialogue
- lift quiet speech
- make soft dialogue louder
- reduce background behind dialogue
- clean up spoken audio
- dialogue leveler lifter
- dialogue leveler cleaner
- set dialogue output gain
- even out voice volume
- improve low dialogue intelligibility
- add clip Dialogue Leveler
- adjust Dialogue Leveler on one clip

## What it does

Set AI Dialogue Leveler parameters.

## Do not use when

Use Dialogue Processor/EQ/dynamics commands for explicit threshold, compression, de-essing or tonal control.

## Preflight and readback

Require a saved local Disk project, checkpoint it independently, and confirm the intended project can close/reopen. Decide each tri-state option explicitly; omitted booleans are preserved, not forced false.
Afterward, require the intended project/timeline—not `Untitled Project`—to reopen. Run `fairlight ai read` on the same ID and verify lifter, cleaner and normalized gain plus all previously existing ClipFX entries. Open the clip in DaVinci Resolve to confirm the effect is recognized/enabled, then audition and render an A/B segment for actual leveling/background behavior and artifacts.

## Public arguments and options

- `--lifter/--no-lifter` (optional) — Lift soft dialogue
- `--cleaner/--no-cleaner` (optional) — Background reduction
- `--gain` (optional) — Output gain (0.0-1.0)
- `--clip` (optional) — Timeline audio clip name or id to target; defaults to the first current-timeline audio clip

## Boundaries and gotchas

- The generated command-index example using `--amount 60` is invalid.
- It ignores playhead and UI selection, so omitting `--clip` can process the wrong dialogue.
- Name selection is case-insensitive exact matching.
- Duplicate names are rejected as ambiguous; an exact item ID is safer.
- Only lifter, cleaner and output gain are supported for writes.
- Preset, advanced rider, gate automation and other advanced parameters cannot be requested here.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight ai dialogue-leveler --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
