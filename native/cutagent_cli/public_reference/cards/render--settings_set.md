# `render settings-set`

Syntax: `cutagent render settings-set [--target VALUE] [--format VALUE] [--codec VALUE] [--name VALUE] [--width VALUE] [--height VALUE] [--fps VALUE] [--video] [--audio] [--audio-codec VALUE] [--audio-bit-depth VALUE] [--audio-sample-rate VALUE] [--full-timeline]`

## Search terms

- configure render settings
- set Deliver output target
- set render resolution frame rate
- enable export video audio
- configure audio codec bit depth
- render format codec selector

## What it does

Configure render settings.

## Do not use when

Do not trust dry-run as validation of the option combination or values; it returns a generic plan before command-specific validation.
Do not change settings while a render is active or without preserving the prior configuration.
Do not assume success proves readback, encoder compatibility, writable output, or an actual render.

## Preflight and readback

Supply only intended fields; omitted booleans remain unchanged.
After execution, rerun `render settings`, compare every requested key, inspect the Deliver page, and perform a short render.

## Public arguments and options

- `--target` (optional) — Output directory
- `--format` (optional) — Output format (mp4, mov, etc.)
- `--codec` (optional) — Codec (H.264, H.265, etc.)
- `--name` (optional) — Output filename
- `--width` (optional)
- `--height` (optional)
- `--fps` (optional)
- `--video/--no-video` (optional)
- `--audio/--no-audio` (optional)
- `--audio-codec` (optional) — Audio codec, e.g. Linear PCM
- `--audio-bit-depth` (optional) — Audio bit depth
- `--audio-sample-rate` (optional) — Audio sample rate in Hz
- `--full-timeline` (optional, default: `false`) — Select the full timeline render range

## Boundaries and gotchas

- Exact help exposes `--target`, `--format`, `--codec`, `--name`, `--width`, `--height`, `--fps`, `--video/--no-video`, `--audio/--no-audio`, `--audio-codec`, `--audio-bit-depth`, and `--audio-sample-rate`.
- Dry-run does not echo selected keys or values.
- Dry-run does not run positive-number validation.
- Dry-run does not reject `--codec` without `--format`.
- `--video`/`--no-video` and `--audio`/`--no-audio` are tri-state; omission leaves each setting untouched.
- `--codec` is the video codec selector and is rejected without `--format`.
- Format matching accepts exact/case-insensitive/normalized labels and matching extensions when format discovery is available.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render settings-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
