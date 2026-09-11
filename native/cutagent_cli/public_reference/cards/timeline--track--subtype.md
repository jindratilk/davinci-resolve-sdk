# `timeline track subtype`

Syntax: `cutagent timeline track subtype TRACK_TYPE INDEX`

## Search terms

- get timeline track subtype
- audio track format
- inspect mono stereo track
- video subtitle subtype
- timeline track management

## What it does

Check a track subtype when available.

## Do not use when

Do not use this to change a subtype or channel format; it is read-only.
Do not assume a null/false/empty subtype means the track is missing or has a specific default.

## Preflight and readback

Before execution, activate the intended timeline; list tracks; verify type, one-based index, and name; and use the audio/Fairlight-specific format commands when a stronger channel-layout contract is needed.

## Public arguments and options

- `TRACK_TYPE` (required) — Track type: video, audio, subtitle
- `INDEX` (required) — Track index

## Boundaries and gotchas

- Index is converted to `int` but not required to be positive and not checked against current track count.
- The command targets only the active timeline and requires one.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent timeline track subtype --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
