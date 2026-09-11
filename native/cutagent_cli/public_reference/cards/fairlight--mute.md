# `fairlight mute`

Syntax: `cutagent fairlight mute INDEX`

## Search terms

- mute audio track
- silence A1
- turn off a Fairlight track
- disable audio track playback
- stop one whole track from sounding
- mute every clip on a track
- temporarily silence dialogue track
- exclude music track from playback
- click the Fairlight track mute control
- set track enabled false
- mute timeline audio lane
- silence track without deleting clips

## What it does

Mute an audio track.

## Do not use when

Use `fairlight unmute INDEX` when the track must be audible again.
Use a clip enable/disable command when only one timeline clip occurrence should be silent. Use `clip audio-gain`, clip volume, fades, or audio automation when the request is attenuation, a fade, or a level change rather than a binary whole-track exclusion.
Do not use this for a video track; the command hard-codes track type `audio`. Use the corresponding timeline video-track state command for picture. Do not use it to mute source channels or change mono/stereo channel mapping.
Do not use this as Control Room or speaker mute. Do not use track mute when the user means Main/bus output mute, because disabling A1 changes which program material reaches the mix and renders.

## Preflight and readback

Before muting, run `fairlight tracks` or `fairlight info INDEX` and identify the intended active timeline, 1-based track index, track name, enabled state, format, and clip count. Track indices can change after tracks are inserted or removed, so do not carry an old index across structural timeline edits. If the current UI page matters to the surrounding workflow, record it; this command can switch to Fairlight and does not restore the previous page.
For a user-facing assurance, play a section containing a known clip from that track and confirm it no longer contributes while other tracks remain audible.
When the mute is temporary, record the original enabled state and restore only tracks that this workflow changed. Use `fairlight unmute INDEX`, verify `enabled:true`, and explicitly switch back with `page switch edit` (or the recorded page) if downstream operations depend on the prior page.

## Public arguments and options

- `INDEX` (required)

## Boundaries and gotchas

- Its dry-run branch does not connect or verify that the requested track actually exists.
- Do not infer that the second invocation changed anything.
- The state applies to the entire track, including clips outside the current visible range and clips added to that track later while it remains disabled.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight mute --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
