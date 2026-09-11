# `fairlight export audio`

Syntax: `cutagent fairlight export audio OUTPUT_PATH [--format VALUE] [--codec VALUE] [--bitdepth VALUE] [--samplerate VALUE]`

## Search terms

- export Fairlight mix
- render timeline audio only
- bounce full mix to file
- create audio mixdown
- save current timeline sound
- export WAV from DaVinci Resolve
- render dialogue and music mix
- deliver audio-only MP4
- print master bus to disk
- export 48 kHz audio
- make final audio file
- render all timeline audio tracks

## What it does

Export the current timeline audio mix through DaVinci Resolve render DaVinci Resolve.

## Do not use when

Do not use this command while the current project's render queue contains jobs that must be preserved; it deletes all of them before rendering. Use explicit `render add`, `render start`, and `render wait` when queue ownership, an in/out range, or an existing Deliver configuration matters. Use `render custom-range` or a configured range job when only part of the timeline should be exported, because this command always selects all frames. Use `fairlight bounce track` or `fairlight bounce mix-to-track` when the result should become a timeline item rather than an external file. Use `render transcript-audio` when the output must follow the transcript-specific imported preset.

## Preflight and readback

Before running, confirm the exact current project/timeline, timeline duration, audible track/bus state, and that no wanted render is active or queued. Audition the beginning/end and measure loudness; the built-in verification proves only that a file was found.

## Public arguments and options

- `OUTPUT_PATH` (required) — Output audio file path
- `--format` (optional, default: `"Wave"`) — Render format
- `--codec` (optional, default: `"Linear PCM"`) — Audio codec
- `--bitdepth` (optional, default: `16`) — Audio bit depth
- `--samplerate` (optional, default: `48000`) — Audio sample rate

## Boundaries and gotchas

- A supported container/profile can still create an audio-only file.
- `--bitdepth` and `--samplerate` are validated only as positive integers.
- The command does not preflight an existing output file or prove it was replaced.
- It does not decode the file, compare duration to the timeline, inspect silence/clipping, or prove every routed track was audible.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight export audio --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
