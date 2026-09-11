# `render resolutions`

Syntax: `cutagent render resolutions [FORMAT_NAME] [CODEC]`

## Search terms

- list render resolutions
- available output dimensions
- resolution by format codec
- QuickTime H.264 resolutions
- Deliver resolution compatibility
- codec-specific dimensions

## What it does

List available render resolutions.

## Do not use when

Do not treat the result as a guarantee that a particular combination will render successfully on the current hardware, media, timeline, or encoder.
Do not use it to change output dimensions; this is a read-only discovery command.

## Preflight and readback

Ensure the intended project is current and the embedded bridge is connected.
Compare the returned dimensions with timeline settings, delivery requirements, pixel aspect, frame rate, encoder restrictions, and the selected render preset.

## Public arguments and options

- `FORMAT_NAME` (optional) — Format (e.g., mp4, QuickTime)
- `CODEC` (optional) — Codec (e.g., H.264, H.265)

## Boundaries and gotchas

- Both filters are optional positional arguments; a codec cannot be supplied independently without occupying the format position.
- Format matching accepts exact key, case-insensitive key, punctuation-insensitive normalized key, or matching extension with an optional leading dot.
- Codec matching accepts exact or case-insensitive description/token and punctuation-insensitive normalized description/token.
- It does not combine or deduplicate results across formats/codecs.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render resolutions --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
