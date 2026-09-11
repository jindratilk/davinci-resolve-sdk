# `fairlight unmute`

Syntax: `cutagent fairlight unmute INDEX`

## Search terms

- unmute Fairlight track
- unmute audio track
- turn audio track back on
- enable A2
- restore sound on audio lane
- hear the dialogue track again
- re-enable music track
- audio track is silent
- clear track mute
- switch on Fairlight track
- enable all clips on audio track
- restore muted audio lane

## What it does

Unmute an audio track.

## Do not use when

Use `fairlight unlock INDEX` when edits are blocked by a track padlock. Enabled and locked are independent: unmuting a locked track makes it audible but still protected from timeline edits.
Use `fairlight monitor mute` or the corresponding monitor-control workflow when the Fairlight control-room/monitor output is muted. `fairlight unmute` targets an individual timeline audio track and does not change monitor mute state.
`fairlight solo` implements isolation by changing enabled states on every audio track; unmuting one lane manually can partially break that solo while leaving other pre-solo states unrestored.
Use `timeline track enable audio INDEX` in a generic timeline workflow, and `timeline track enable video INDEX` for a video track. `fairlight unmute` cannot target video.
It enables the entire lane; diagnose the narrower cause first.
Do not use a cached index after adding, deleting, duplicating, or reordering audio tracks.

## Preflight and readback

Before mutation, run `fairlight info INDEX` or `fairlight tracks` and confirm the current timeline, row identity, `enabled:false`, lock state, clip count, and intended scope.
Tell an interactive user that DaVinci Resolve may switch to the Fairlight page.
Audition through the track and verify that downstream bus/monitor routing is also audible.
Save the project if the enabled state is part of the intended deliverable.

## Public arguments and options

- `INDEX` (required)

## Boundaries and gotchas

- All clips on A2 are affected together; no clip name, time range, or selection limits the scope.
- Dry-run validates only `index >= 1`.
- The command acts only on the active timeline and offers no `--timeline` option.
- Refresh `fairlight tracks` after `fairlight add`, `delete`, `track duplicate`, or `track-order move`.
- Readback is polled for up to one second, unlike `fairlight unlock`, which checks lock state only once.
- It confirms desired state but does not prove a new mutation occurred.
- Unmute does not unlock.
- Unmute does not guarantee audible output.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight unmute --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
