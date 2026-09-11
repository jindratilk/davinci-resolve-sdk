# `fairlight track height`

Syntax: `cutagent fairlight track height INDEX [--size VALUE]`

## Search terms

- inspect audio track display size
- how tall is A1
- Fairlight waveform lane height
- audio clip height setting
- per-track adjusted height
- resize Fairlight track
- make audio track taller
- shrink audio lane
- expand waveform display
- Fairlight track height pixels
- set audio track height
- restore default audio lane height

## What it does

Read Fairlight track height state, and report resize availability.

## Do not use when

Do not pass `--size` expecting a preset or pixel resize. Resize the audio track manually on the Fairlight page when visible GUI height is the required outcome.
A per-track value of 0 is a default/unadjusted marker, not a zero-pixel invisible track.
Height is not visibility, enable, mute, lock or waveform zoom. Use `fairlight mute`/`unmute`, enable/disable or lock/unlock for those separate states.
Use `fairlight tracks` when the primary need is the audio-track inventory, names, formats, clip counts and enabled/locked state.
Do not use height readback to prove a GUI resize just occurred.

## Preflight and readback

Before reading, confirm the active project and timeline and run `fairlight tracks` so the selected 1-based index is unambiguous.
Run without `--size` and inspect the complete `height` object.
If the user needs the current visual height, inspect the Fairlight GUI manually.

## Public arguments and options

- `INDEX` (required) — Audio track index
- `--size` (optional) — Requested track height preset or pixel value

## Boundaries and gotchas

- The write/blocker branch does not validate index existence.
- `--size` failures describe unsupported resizing even for a nonexistent track.
- `--size` is an unparsed string.
- The CLI does not distinguish named presets from numeric-looking values and does not normalize units.
- Do not attribute the global value solely to the selected track.
- It does not mean the lane has zero height.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight track height --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
