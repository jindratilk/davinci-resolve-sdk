# `render subtitles`

Syntax: `cutagent render subtitles [--enable] --format VALUE`

## Search terms

- configure subtitle export
- SubtitleFormat setting
- burn in captions render
- embedded captions export
- separate subtitle file
- Deliver subtitle options
- disable subtitle export

## What it does

Configure subtitle export settings.

## Do not use when

Do not use a format spelling that has not been confirmed for the current DaVinci Resolve version; the CLI does not validate the documented set.
Do not assume enabling export creates captions or subtitle tracks.

## Preflight and readback

Before execution, capture `render settings`, inspect subtitle tracks and timeline content, and verify container/codec support plus required sidecar format/location behavior.
Use the exact documented case-sensitive token.

## Public arguments and options

- `--enable/--disable` (optional, default: `true`) — Enable or disable subtitle export
- `--format` (required) — BurnIn|EmbeddedCaptions|SeparateFile

## Boundaries and gotchas

- Exact help is `cutagent render subtitles --format FORMAT [--enable/--disable]`.
- `--format` is required even when disabling export.
- Dry-run does not inspect settings, formats, codecs, subtitle tracks, captions, or output paths.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`

## Examples

- `cutagent render subtitles --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
