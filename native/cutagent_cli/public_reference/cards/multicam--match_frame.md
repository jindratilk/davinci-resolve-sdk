# `multicam match-frame`

Syntax: `cutagent multicam match-frame [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--angle VALUE] [--record-frame VALUE] [--timeline VALUE] [--timeline-frame VALUE] [--media-type VALUE]`

## Search terms

- multicam match frame
- exact angle source
- source item frame
- multicam gap detection

## What it does

Match a multicam frame to its source.

## Do not use when

Do not guess the angle for timeline selector matching when the selector cannot be decoded. Use exact multicam name/media ID/sequence ID when names are ambiguous.

## Preflight and readback

Inspect the multicam first. After matching, require item ID, media ID, item index, timing, source-in, and computed source frame before applying source properties, grades, RAW settings, or edits.

## Public arguments and options

- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--angle` (optional) — One-based angle; optional when timeline selector is decodable
- `--record-frame` (optional) — Frame relative to the multicam start
- `--timeline` (optional) — Timeline name for timeline-to-source match frame
- `--timeline-frame` (optional) — Absolute timeline frame
- `--media-type` (optional, default: `"video"`) — video or audio

## Boundaries and gotchas

- Angles are one-based and source item indices are zero-based.
- `--media-type` is `video` or `audio`.

## Examples

- `cutagent multicam match-frame --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
