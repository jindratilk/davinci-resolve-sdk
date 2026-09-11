# `render codecs`

Syntax: `cutagent render codecs FORMAT_NAME [--media VALUE]`

## Search terms

- list render codecs
- codecs for QuickTime
- codecs for MP4
- DaVinci Resolve codec availability
- render format codec matrix
- codec selector values
- query Deliver codecs

## What it does

List available video and audio codecs for a format.

## Do not use when

Do not assume a codec listed for one container is valid for another container.
Do not use global `--dry-run` expecting cached or simulated data; this command still connects and performs the same read.
Do not infer resolution, alpha, audio-layout, encoder-profile, or delivery compatibility from codec presence alone.

## Preflight and readback

Record DaVinci Resolve version/edition, host platform, project context, and relevant hardware/encoder environment if the result will drive automation.
After the query, preserve both `codec` and `description` fields.

## Public arguments and options

- `FORMAT_NAME` (required) — Format name (e.g., mp4, QuickTime)
- `--media` (optional, default: `"video"`) — Codec inventory: video or audio.

## Boundaries and gotchas

- No command-specific dry-run branch exists.
- With available formats, selection accepts exact label, case-insensitive label, normalized label, or matching extension with/without a leading dot.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render codecs --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
