# `fairlight vca assign`

Syntax: `cutagent fairlight vca assign [VCA] [--track VALUE]`

## Search terms

- assign track to VCA
- add audio track to VCA
- put dialogue tracks under VCA
- VCA group assignment
- link A1 to VCA 1
- control several tracks with one fader
- add music track to VCA fader
- create Fairlight VCA membership
- route track to VCA
- remove track from VCA
- VCA master fader
- Fairlight VCA automation

## What it does

Check Fairlight VCA availability.

## Do not use when

That command is read-only and reports label-pool evidence; it still cannot prove active VCA objects or memberships.
Do not use `fairlight group assign` as a substitute. Fairlight edit/link groups and Fairlight VCAs are different concepts, and group assignment is independently unsupported through the current command surface.
Use `fairlight bus list` for readable bus/main-output labels. A VCA controls member faders without being an audio-routing destination; a bus receives/routs audio. Do not translate “VCA” into “bus” unless the user explicitly accepts the different mix behavior.
Use individual `fairlight mixer fader`, mute/unmute, pan, or automation commands only when the user wants per-track changes and the exact relevant route is supported.

## Preflight and readback

Before calling, determine whether the user truly needs VCA membership rather than a bus, edit group, track folder, or one-time relative fader adjustment.
If label context is useful, run `fairlight vca list` on the active local Disk timeline. Treat its rows only as label-pool strings. A default `VCA 1` label is not evidence that VCA 1 is active, that a control strip exists, or that any track belongs to it.
There is no project-state “after” readback because no mutation is attempted. If a human performs the assignment in DaVinci Resolve, verify membership, relative fader behavior, mute/solo behavior, automation interaction, and a render/audition in the GUI. `fairlight vca list` alone cannot verify that manual change.

## Public arguments and options

- `VCA` (optional) — VCA name
- `--track/-t` (optional) — Audio track index

## Boundaries and gotchas

- `--dry-run` does not turn this into a successful plan.
- The labels do not contain assignment state, fader state, mute, solo, or creation state.
- That does not mean the two-track timeline had 128 configured VCAs.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight vca assign --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
