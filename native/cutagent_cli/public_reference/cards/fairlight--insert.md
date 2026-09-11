# `fairlight insert`

Syntax: `cutagent fairlight insert MEDIA_PATH [--start-offset-samples VALUE] [--duration-samples VALUE]`

## Search terms

- place WAV on current Fairlight track
- add sound to selected audio destination
- overwrite audio with external file
- drop sound effect at cursor
- place full audio file on A1
- split existing audio around inserted clip
- add ambience at current time
- use current Fairlight source track

## What it does

Insert audio at the playhead on the current Fairlight track.

## Do not use when

Use `timeline playhead set` before this command when the record position must be explicit. Use a separate destination track for layering.

## Preflight and readback

Global dry-run is useful only for argument echo; it does not check the file, selector, timeline, or source bounds.
Audition/render the result, especially channel mapping and boundaries.

## Public arguments and options

- `MEDIA_PATH` (required) — Audio file path
- `--start-offset-samples` (optional, default: `0`) — Sample offset within source media
- `--duration-samples` (optional, default: `0`) — Duration to insert in samples (0 = full available duration)

## Boundaries and gotchas

- “Current Fairlight track” means DaVinci Resolve's source-track selector, not merely the active timeline's first audio track, a clicked track header, the selected clip, or the only existing audio track.
- Inserting into occupied time is destructive to that range.
- The overlap edit changed three item signatures even though only one new source was requested.
- Verification does not require item count to increase when a basename-matched changed candidate exists.
- They do not prove source path, Media Pool identity, channel mapping, source in/out samples, waveform content, or audio audibility.
- The command does not prevalidate path existence, readability, audio format, nonnegative offsets/durations, or whether offset plus duration fits the source.
- The command does not restore the previous position.
- The practical blocker is selector/file/timeline readiness, not a Studio-only gate.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fairlight insert --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
