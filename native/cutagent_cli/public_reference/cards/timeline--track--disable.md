# `timeline track disable`

Syntax: `cutagent timeline track disable TRACK_TYPE INDEX`

## Search terms

- disable timeline track
- mute timeline audio track
- turn off video track
- track enabled state
- hide subtitle track
- timeline track management

## What it does

Mute a track.

## Do not use when

Do not use global `--dry-run` as a preview.

## Preflight and readback

For video tracks, note that the UI may have been left on the Edit page.

## Public arguments and options

- `TRACK_TYPE` (required)
- `INDEX` (required)

## Boundaries and gotchas

- Index must be an integer at least 1.
- It does not restore the prior page afterward.
- Audio and subtitle tracks do not trigger a page switch.
- The command does not save the project.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline track disable --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
