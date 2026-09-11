# `fairlight voice-isolation set`

Syntax: `cutagent fairlight voice-isolation set TRACK [--enable] [--amount VALUE]`

## Search terms

- enable Voice Isolation on audio track
- set track voice isolation
- isolate dialogue from background noise
- reduce room sound on speech track
- clean up noisy dialogue track
- set Voice Isolation strength
- remove background from A2 speech
- disable track Voice Isolation
- turn off voice cleanup
- set dialogue isolation percentage
- apply AI speech isolation to whole track
- make voices clearer on Fairlight track

## What it does

Set voice isolation state for an audio track.

## Do not use when

Use `clip voice-isolation NAME` or `fairlight ai voice-isolation AMOUNT --clip NAME` when only one timeline item should be processed.
Use `fairlight ai dialogue-leveler` when the problem is inconsistent speech level rather than background/room/noise separation. Use Fairlight EQ for tonal correction and dynamics for compression/gating. Voice Isolation can create artifacts and is not a substitute for those controls.
Use `fairlight voice-isolation get TRACK` for read-only inspection.
Use `fairlight unmute` when the track is disabled, and `fairlight unlock` when it is edit-locked. Voice Isolation does not change audibility or lock state.
Its default amount is 100, while DaVinci Resolve normalizes disabled Voice Isolation to amount 0, causing an exact-readback failure. Use `--disable --amount 0`.
Do not trust a dry-run as range or target validation. It accepts nonexistent positive tracks and out-of-range amounts.

## Preflight and readback

Before mutation, run `fairlight tracks` to prove the active timeline and the target's current 1-based audio-track identity. Then run `fairlight voice-isolation get TRACK` and require a normal `isEnabled`/`amount` dictionary, not a generic `state:false`.
Audition or render a representative speech section before changing the effect. Choose the lowest useful amount; aggressive isolation can damage consonants, ambience continuity, music, or overlapping speakers.
For disabling, specify amount 0 explicitly.
Run a separate `voice-isolation get` and audition/render the same section. Save the project after the desired state is confirmed.
Immediately run the getter and restore the pre-state explicitly; do not assume an error means no mutation.

## Public arguments and options

- `TRACK` (required) — Audio track index
- `--enable/--disable` (optional, default: `true`) — Enable or disable voice isolation
- `--amount` (optional, default: `100.0`) — Voice isolation amount

## Boundaries and gotchas

- Fractional negatives between -1 and 0 also truncate to 0 before range validation.
- `--enable/--disable` defaults to enable, and `--amount` defaults to 100.
- Running only `set 2` turns the effect fully on.
- `--disable` does not alter the amount default.
- It leaves the enable flag true while strength is zero; do not infer disabled state from amount alone.
- Both getter and setter must be available before writing.
- It does not switch to Fairlight.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight voice-isolation set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
