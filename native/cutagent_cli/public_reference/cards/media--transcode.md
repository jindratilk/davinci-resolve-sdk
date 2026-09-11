# `media transcode`

Syntax: `cutagent media transcode NAME --output VALUE [--format VALUE] [--codec VALUE]`

## Search terms

- convert Media Pool clip to another format
- export standalone converted media
- create h264 copy from source clip
- transcode footage file
- make mp4 from Media Pool item
- encode clip to new codec
- create delivery copy of source media

## What it does

Transcode media pool clip.

## Do not use when

Use the Deliver/render commands when encoding a timeline, an in/out range, grades, titles, mixed audio, or a controlled render preset. Use `audio reverb`, `audio duck`, or other file-processing commands for their specific audio transforms. Use `media replace`/`media relink` only after a separately created file should become the Media Pool source.

## Preflight and readback

After success, independently check that the output file exists, is nonempty, decodes, and has the expected duration, streams, codec, frame rate, resolution, color, and audio. Import or relink it only as a separate deliberate step.

## Public arguments and options

- `NAME` (required) — Clip name
- `--output` (required) — Output path
- `--format` (optional) — Optional transcode format
- `--codec` (optional) — Optional transcode codec

## Boundaries and gotchas

- `--format` and `--codec` are unconstrained strings.
- The command has no local `--json` or `--dry-run` option in its own help.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent media transcode --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
