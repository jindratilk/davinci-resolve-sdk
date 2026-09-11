# `timeline track delete`

Syntax: `cutagent timeline track delete TRACK_TYPE INDEX`

## Search terms

- delete timeline track
- remove video track
- remove audio track
- remove subtitle track
- destructive track management
- shift timeline track indexes

## What it does

Delete a timeline track.

## Do not use when

Do not use this merely to hide, mute, disable, lock, or clear a track. Deleting the track is structurally destructive, can remove all of its timeline items, and can renumber later tracks.
Do not run it from an assumed index. The command does not validate the type, require a positive index, inspect contents, confirm emptiness, prompt, or create a checkpoint.

## Preflight and readback

After execution, list tracks again and verify that the intended track alone is gone, later indexes shifted as expected, no required items/routing were lost, and all subsequent commands use fresh indexes. Inspect the real timeline before saving or reporting success.

## Public arguments and options

- `TRACK_TYPE` (required) — Track type: video, audio, subtitle
- `INDEX` (required) — Track index

## Boundaries and gotchas

- No `--force` or interactive confirmation is required by this command itself.
- The command cannot prove which named track was deleted.
- It does not save the project.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent timeline track delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
