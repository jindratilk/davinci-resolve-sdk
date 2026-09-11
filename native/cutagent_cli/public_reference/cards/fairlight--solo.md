# `fairlight solo`

Syntax: `cutagent fairlight solo INDEX`

## Search terms

- solo audio track
- hear only A1
- mute every other audio track
- isolate dialogue track
- listen to music track alone
- enable one track and disable the rest
- audition one Fairlight track
- temporarily silence competing tracks
- isolate one timeline audio lane
- solo voiceover for review
- listen to one stem
- make only track 2 audible

## What it does

Solo an audio track by disabling all other audio tracks.

## Do not use when

This emulation rewrites track enabled/mute state and must be explicitly restored.
Use `fairlight mute INDEX` or `unmute INDEX` when only one track's enabled state should change. Use clip enable/gain commands when only one timeline occurrence is the target. Use bus/Main or monitor controls when the requested isolation is downstream of track enable.
Do not use this to solo multiple tracks; it accepts one index and disables every other audio track.
That destroys any tracks that were intentionally muted before solo.

## Preflight and readback

Before running, list all audio tracks and enabled states and verify the active timeline/target index. Save the project if enabled-state changes matter, and record the current UI page. Avoid structural track edits until restoration is complete.
After solo, verify that the target is enabled, every other audio track is disabled, clip counts are unchanged, and the audible mix contains only the intended track.
Switch back to the prior page explicitly if needed.

## Public arguments and options

- `INDEX` (required) — Audio track index to solo

## Boundaries and gotchas

- Enabled state can affect timeline output/render, unlike a monitor-only audition control.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight solo --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
