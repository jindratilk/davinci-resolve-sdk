# `fairlight mixer pan`

Syntax: `cutagent fairlight mixer pan [--track VALUE] [--bus VALUE] [--pan VALUE] [--angle VALUE] [--spread VALUE]`

## Search terms

- pan Fairlight track left
- pan audio track right
- center A1 mixer pan
- set mono track balance
- move whole dialogue track left
- set Fairlight 2D pan
- control Main bus pan
- set Bus 1 panner
- change surround pan angle
- set 3D panner spread
- place every clip on a track in stereo field
- set static track pan

## What it does

Set and read a Fairlight audio-track mixer pan in DaVinci Resolve.

## Do not use when

Set the track panner manually in DaVinci Resolve when audible placement must be guaranteed.
Use `clip audio-pan` for one timeline occurrence or `fairlight audio-pan batch` for a selected collection of clip occurrences; those target clip effect payloads rather than the whole track. Use automation commands when pan must vary over time. Use source/channel-mapping commands when the problem is incorrect mono/stereo channel interpretation rather than a panner control. Use fader/gain commands for loudness changes.
Do not use `--bus Main`, `--bus "Bus 1"`, or another FlexBus: every bus branch is deliberately unavailable. Do not use `--angle` or `--spread` for stereo, surround, adaptive, or 3D placement. Those options are accepted only so the command can return a structured unsupported boundary.

## Preflight and readback

Before a track read/write, save the intended local Disk project, list audio tracks, and confirm the 1-based index, stable track ID, subtype, channel count, item materialization, routing, and current visible panner.
Reopen Fairlight, inspect the actual panner and play a controlled mono signal while observing both post-pan Bus/Main channels. Render and compare left/right RMS/peaks when the render route works.

## Public arguments and options

- `--track/-t` (optional) — Audio track index
- `--bus` (optional) — Bus/main output name
- `--pan` (optional) — Requested 2D Left / Right pan value
- `--angle` (optional) — Requested 3D pan angle
- `--spread` (optional) — Requested 3D pan spread

## Boundaries and gotchas

- Per-channel integers do not establish DaVinci Resolve's stereo/surround panner semantics.
- `--pan` is rounded to one decimal.
- Adding `--bus` selects the bus blocker before track, 3D, range, or mutual-exclusion validation.
- Adding either `--angle` or `--spread` selects the 3D blocker even if `--pan` is also present.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight mixer pan --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
