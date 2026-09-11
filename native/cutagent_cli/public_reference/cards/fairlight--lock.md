# `fairlight lock`

Syntax: `cutagent fairlight lock INDEX`

## Search terms

- lock Fairlight audio track
- protect A1 from edits
- prevent audio track changes
- lock dialogue track
- freeze track editing
- make audio lane read-only
- protect music track
- set track lock state
- lock A2 before ripple edit
- prevent clip moves on track
- secure finished audio mix lane
- toggle audio track padlock on

## What it does

Lock an audio track.

## Do not use when

Use `fairlight mute`/`unmute` for audibility, `fairlight solo` plus `solo-restore` for isolating playback, and track enable/disable commands when the intended state is enabled rather than editable. Use timeline/video-track lock commands when the target is not audio.

## Preflight and readback

Ensure the user means that exact active timeline; indices can differ between timelines. Global dry-run can confirm a positive parsed index but does not prove the track exists. Record the prior state so cleanup/restoration uses `fairlight unlock` only when the track was originally unlocked.

## Public arguments and options

- `INDEX` (required)

## Boundaries and gotchas

- If the getter is unavailable, only an exact setter return of `false` is rejected.
- The wrapper does not explicitly save the project.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fairlight lock --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
