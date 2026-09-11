# `fairlight monitor mute`

Syntax: `cutagent fairlight monitor mute [--enable]`

## Search terms

- mute Control Room monitors
- unmute Fairlight speakers
- silence studio monitor output
- turn off listening speakers
- mute DaVinci Resolve monitoring
- enable monitor mute
- disable monitor mute
- stop sound from speakers without changing mix
- toggle Fairlight monitor mute
- mute playback monitoring only
- unmute hardware monitor path
- set Control Room mute button

## What it does

Check Fairlight monitor mute availability.

## Do not use when

Use the visible Fairlight Control Room mute/DIM controls or the physical monitor controller/audio interface when the listening output must actually be silenced or restored. Use operating-system audio controls for device-level mute. Verify visually and audibly before assuming speakers are safe.
Use `fairlight mute`/track enable-mute commands when one audio track should stop contributing to the mix, and clip enable/gain commands when one occurrence is the target. Use Main/bus controls when the program mix itself must be muted. Those operations can affect renders; Control Room mute should affect monitoring only.
Use `fairlight monitor level` only to receive its separate unsupported level boundary.
Do not omit the option expecting a read.

## Preflight and readback

For a real manual mute, identify whether the user means monitor-only, a track, a bus/Main mix, or the operating-system output. Record the current speaker/control state and avoid using loud program material as the test.

## Public arguments and options

- `--enable/--disable` (optional, default: `true`) — Requested monitor mute state

## Boundaries and gotchas

- `--enable/--disable` controls the requested **mute state**.
- `--disable` means disable mute (unmute), not disable monitoring or disable audio.
- Falling back to those changes the mix rather than only the listening path.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight monitor mute --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
