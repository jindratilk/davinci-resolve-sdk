# `render audio`

Syntax: `cutagent render audio OUTPUT_PATH [--format VALUE] [--codec VALUE] [--bitdepth VALUE] [--samplerate VALUE]`

## Search terms

- render timeline audio only
- export WAV from timeline
- Linear PCM audio render
- audio-only Deliver job
- clear render queue audio
- 24-bit 96 kHz export
- render audio file path
- DaVinci Resolve audio bounce

## What it does

Render audio only from the timeline.

## Do not use when

Do not use while the render queue contains jobs that must be preserved. The command clears the queue and does not restore those jobs.
Do not use while an unrelated render should continue. Cleanup attempts to stop active rendering before clearing jobs.
Do not treat dry-run as validation of output writability, format/codec support, bit depth, or sample rate.
Do not use for a marked range, separate stems, individual timeline tracks, or a video-plus-audio deliverable; this command renders all timeline frames into one audio-only job.

## Preflight and readback

Before execution, save or record every existing render job, confirm no unrelated render is active, identify the active project/timeline, query available formats/codecs, confirm positive bit depth/sample rate, and choose a writable output path with an appropriate extension.
Record the current Deliver page, render mode, format/codec, and settings. Back up any custom render configuration that cannot be reconstructed safely.
After execution, verify the returned file exists and inspect its container, codec, duration, channel layout, sample rate, bit depth, audible content, and sync. Confirm the original Deliver context was restored and review the queue, which will not contain the original jobs.

## Public arguments and options

- `OUTPUT_PATH` (required) — Output file path
- `--format` (optional, default: `"Wave"`) — Audio format
- `--codec` (optional, default: `"Linear PCM"`) — Audio codec
- `--bitdepth` (optional, default: `16`) — Bit depth
- `--samplerate` (optional, default: `48000`) — Sample rate

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent render audio --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
