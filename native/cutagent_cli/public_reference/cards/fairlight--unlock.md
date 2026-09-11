# `fairlight unlock`

Syntax: `cutagent fairlight unlock INDEX`

## Search terms

- unlock Fairlight track
- unlock audio track
- unlock A2
- remove track lock
- allow edits on audio track
- make audio lane editable
- clear padlock on audio track
- unlock entire dialogue track
- unlock music track
- audio track is locked
- cannot edit clips on audio track
- enable editing on Fairlight lane

## What it does

Unlock an audio track.

## Do not use when

Use `fairlight unmute INDEX` when the track is disabled/muted. Lock and enabled state are independent: an unlocked track can remain inaudible, and a locked track can remain audible.
Use `timeline track unlock video INDEX` for a video track. `fairlight unlock` is the audio-only convenience surface.
Use `fairlight lock INDEX` when the user wants to protect a complete audio lane from edits. Unlock is not a toggle and will never lock an already-unlocked track.
Its scope is exactly the active timeline's audio-track lock flag.
Do not use a remembered index after a track add/delete/reorder.

## Preflight and readback

Record the active timeline name.
If the unlock was preparation for a later mutation, re-check the target identity before executing that later command.
Save the project when the unlocked state must persist as part of the deliverable. If the user intended only a temporary unlock, perform the protected edit, verify it, and restore the original lock with `fairlight lock INDEX`.

## Public arguments and options

- `INDEX` (required)

## Boundaries and gotchas

- The index is 1-based and audio-only.
- Dry-run checks only `index >= 1`.
- There is no `--name`, `--track-id`, or `--timeline` option.
- It cannot address an inactive timeline without switching first.
- Do not infer that the track was previously locked from the sentence “Unlocked audio track N.”

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight unlock --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
