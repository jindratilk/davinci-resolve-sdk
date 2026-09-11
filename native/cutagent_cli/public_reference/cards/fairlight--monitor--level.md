# `fairlight monitor level`

Syntax: `cutagent fairlight monitor level [--level VALUE]`

## Search terms

- set Fairlight monitor volume
- lower studio speakers
- turn down DaVinci Resolve monitoring
- adjust Control Room slider
- change listening volume without changing mix
- dim monitor output
- control speaker level
- set Fairlight monitoring gain
- lower playback speakers only
- adjust Bus monitor level
- query control room level

## What it does

Check Fairlight monitor level availability.

## Do not use when

That reader still cannot return the current Control Room level.
Use the visible Fairlight Control Room slider or the external monitor controller/audio interface when the listening level must actually change. Use operating-system audio controls for macOS/Windows device volume. Those states are outside this public CLI command.
Use `fairlight mixer fader`, track/clip gain, automation, or Main mix controls when the requested change must affect the program mix or render. Monitor level is listening-path-only; substituting a mix fader changes delivered audio. Conversely, do not use this monitor command when the user asks to make a clip or track quieter.
Use `fairlight monitor mute` only to receive the corresponding explicit unsupported boundary; it cannot mute. DIM, speaker-set selection and fold-down also require manual DaVinci Resolve/hardware control.

## Preflight and readback

For a real manual adjustment, first distinguish Control Room monitoring from track/bus/master mix level and record the current hardware/output device. Change the visible monitor control, then verify the numeric UI value and audition at a safe reference signal.

## Public arguments and options

- `--level/--level-db` (optional) — Monitor/control-room level in dB

## Boundaries and gotchas

- `--dry-run` is not a successful plan.
- They are explicitly unverified and must not be patched to emulate monitor control.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight monitor level --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
