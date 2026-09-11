# `render archive-settings`

Syntax: `cutagent render archive-settings [--target VALUE] [--name VALUE] [--format VALUE] [--codec VALUE] [--audio-codec VALUE] [--audio-bit-depth VALUE] [--audio-sample-rate VALUE] [--width VALUE] [--height VALUE] [--fps VALUE] [--separate-audio-tracks]`

## Search terms

- configure archive render settings
- high quality archive master
- ProRes archive export
- Linear PCM render audio
- separate embedded audio tracks
- main mix archive audio
- archive render resolution
- archive render frame rate
- Deliver page archive preset

## What it does

Configure archive render settings.

## Do not use when

Do not use this as proof that all timeline audio tracks will be embedded separately.
Do not use arbitrary format or codec labels without first querying the formats/codecs available in the connected DaVinci Resolve project.
Do not trust dry-run to reject invalid width, height, or frame rate.
Do not enqueue or start a render until the resulting Deliver-page settings, destination, filename, channel layout, and expected storage requirements have been inspected.

## Preflight and readback

Before execution, record current render format/codec and settings, available formats/codecs, output destination, intended archive naming, resolution/frame rate, audio layout, bit depth, sample rate, and available disk space.
Use `render formats`, `render codecs`, and a dry-run to resolve the intended route. Choose `--main-mix-audio` unless a separately prepared DaVinci Resolve preset handles per-track embedded audio.
Confirm the selected format/codec, output path/name, video/audio flags, resolution/frame rate, and actual audio channel mapping before adding a job. Render and inspect a short archive sample.

## Public arguments and options

- `--target` (optional) — Output directory
- `--name` (optional) — Output filename
- `--format` (optional, default: `"QuickTime"`) — Archive container format
- `--codec` (optional, default: `"Apple ProRes"`) — Archive video codec selector
- `--audio-codec` (optional, default: `"Linear PCM"`) — Archive audio codec
- `--audio-bit-depth` (optional, default: `32`) — Audio bit depth
- `--audio-sample-rate` (optional, default: `48000`) — Audio sample rate in Hz
- `--width` (optional)
- `--height` (optional)
- `--fps` (optional)
- `--separate-audio-tracks/--main-mix-audio` (optional, default: `true`) — Request separate embedded timeline audio tracks when DaVinci Resolve API supports it

## Boundaries and gotchas

- `--main-mix-audio` changes that request to the supported main rendered mix.
- Format selectors resolve by exact, case-insensitive, normalized label, or extension match when format enumeration is available.
- Codec selectors resolve by exact, case-insensitive, or normalized description/value match for the selected format.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render archive-settings --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
