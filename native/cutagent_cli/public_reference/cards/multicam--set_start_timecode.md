# `multicam set-start-timecode`

Syntax: `cutagent multicam set-start-timecode --start-timecode VALUE [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE]`

## Search terms

- multicam start timecode
- change multicam timecode
- preserve source offsets
- sequence media extents

## What it does

Change the multicam start timecode.

## Do not use when

Do not accept a malformed or frame-rate-invalid timecode.

## Preflight and readback

Capture the sequence start and item timing before mutation. Afterwards require the requested timecode, preserved relative item offsets, consistent video/audio bindings, and reopen verification.

## Public arguments and options

- `--start-timecode` (required)
- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)

## Boundaries and gotchas

- `--start-timecode` is required.

## Examples

- `cutagent multicam set-start-timecode --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
