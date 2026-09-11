# `clip voice-isolation`

Syntax: `cutagent clip voice-isolation [NAME] [--enable] [--amount VALUE]`

## Search terms

- isolate dialogue from background noise
- clean up voice on one clip
- enable DaVinci Resolve voice isolation
- remove music behind speech
- suppress non-speech in audio occurrence
- set voice isolation amount
- turn off AI dialogue cleanup
- make spoken voice clearer
- reduce room/background sound on clip

## What it does

Check clip voice isolation.

## Do not use when

Use Fairlight track-level processing when every clip on a track needs the same cleanup, automation when strength must vary over time, and manual EQ/dynamics/noise tools when deterministic frequency/dynamics control is required. Use clip gain/normalize for level alone; Voice Isolation changes content classification, not merely loudness. Do not assume it repairs clipping, reverb, sync, or channel mapping.

## Preflight and readback

Listen for pumping, missing words, ambience discontinuity, and phase/channel artifacts; meter comparison alone is insufficient. Restore both original fields, verify readback, and save only after the expected audio returns.

## Public arguments and options

- `NAME` (optional) — Clip name (or current clip)
- `--enable/--disable` (optional) — Enable or disable voice isolation
- `--amount` (optional) — Isolation strength 0-100

## Boundaries and gotchas

- Global `--dry-run` is broken and mutating for this command.
- `--enable` without `--amount` preserves the current amount when the getter works.
- `--amount` without an enable/disable switch preserves the current `isEnabled`.
- Changing amount on a disabled clip does not necessarily make processing audible.
- If the getter exists but is unsupported/throws, an explicit enable plus amount can still be sent using defaults; amount-only needs reliable current state and can fail.

## Examples

- `cutagent clip voice-isolation --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
