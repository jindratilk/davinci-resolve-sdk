# `timeline track enable`

Syntax: `cutagent timeline track enable TRACK_TYPE INDEX`

## Search terms

- enable timeline track
- unmute audio track
- turn on video track
- track enabled readback
- enable subtitle track
- timeline track management

## What it does

Enable a track.

## Do not use when

Do not use global `--dry-run` as a preview.

## Preflight and readback

Before execution, activate and save the exact timeline; freshly list tracks; verify the type, one-based index, name, item count, and current enabled state; understand how re-enabling picture/audio/subtitles affects playback and renders; and avoid running this command under dry-run.
For a video track, check the UI because the command can leave DaVinci Resolve on the Edit page.

## Public arguments and options

- `TRACK_TYPE` (required)
- `INDEX` (required)

## Boundaries and gotchas

- Index must be an integer at least 1.
- Audio and subtitle enable operations do not request a page switch.
- Re-enabling a track can unexpectedly restore it to playback/render output; the command does not inspect downstream routing or mix state.
- It does not save the project.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline track enable --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
