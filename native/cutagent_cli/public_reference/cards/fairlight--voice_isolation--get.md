# `fairlight voice-isolation get`

Syntax: `cutagent fairlight voice-isolation get TRACK`

## Search terms

- get track voice isolation
- check if voice isolation is enabled
- inspect dialogue isolation amount
- show voice cleanup strength on A1
- is Voice Isolation on for this audio track
- get noise removal amount for dialogue track
- check track-level speech isolation
- verify voice isolation after setting
- see Voice Isolation setting on empty track
- track voice isolation readback

## What it does

Read voice isolation state for an audio track.

## Do not use when

Use `fairlight voice-isolation set TRACK` for a track-wide write.
Use `clip voice-isolation NAME` when the user means one timeline item rather than the complete audio track. Use `fairlight ai voice-isolation AMOUNT --clip NAME` for the Fairlight clip-oriented AI command.
Do not interpret a disabled track-level result as proof that no clip on the track has Voice Isolation.
It does not validate the audio-track count and can return a successful `state:false` for an invalid index.

## Preflight and readback

Before reading, run `fairlight tracks` and confirm the active timeline, the intended row's current 1-based index, name, clip count, and existence. This validation is mandatory because the getter command itself does not reject out-of-range indices reliably.
When the audible result matters, audition or render speech and compare against bypass.

## Public arguments and options

- `TRACK` (required) — Audio track index

## Boundaries and gotchas

- Do not mistake that for a real disabled track state.
- The shape difference is currently the best immediate clue, but preflight track inventory remains the required proof.
- Downstream code must branch on the presence of `isEnabled` and `amount`.
- Do not confuse it with a clip command that may expose a normalized 0–1 interface.
- This getter does not switch to the Fairlight page; current page, selection, and playhead remain untouched.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight voice-isolation get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
