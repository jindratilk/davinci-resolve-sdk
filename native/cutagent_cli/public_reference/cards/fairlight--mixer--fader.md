# `fairlight mixer fader`

Syntax: `cutagent fairlight mixer fader [--track VALUE] [--bus VALUE] [--level VALUE]`

## Search terms

- set Fairlight track fader
- lower audio track volume
- raise mixer channel level
- attenuate whole audio track
- set every channel lane to same level
- change A1 mixer fader
- set Main output gain context
- lower master bus fader
- inspect Fairlight mixer lane values
- control non-main FlexBus fader

## What it does

Set and read a Fairlight audio-track fader and main-output gain context.

## Do not use when

Use `clip audio-gain` or the corresponding Fairlight clip-gain command when only one timeline item should change. A track fader affects the whole track's mix contribution, including every clip routed through that strip.
Use `fairlight mixer pan` for pan.
Do not use the `--bus Main` branch as a claimed master-bus fader edit.
The public branch fails before connecting because non-main bus graph/fader storage is unmapped.

## Preflight and readback

Before a track write, confirm the active project/timeline and exact track index/name/format with `fairlight tracks`, then run this command without `--level`.
Confirm multi-channel balance, automation, neighbors and routing were not disturbed.
Restore the exact prior scalar, not an assumed 0.0.

## Public arguments and options

- `--track/-t` (optional) — Audio track index
- `--bus` (optional) — Bus/main output name
- `--level/--level-db` (optional) — Requested fader level in dB

## Boundaries and gotchas

- Track and bus are mutually exclusive.
- Omitting `--level` means read.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight mixer fader --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
