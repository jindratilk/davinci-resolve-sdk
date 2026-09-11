# `fairlight track show`

Syntax: `cutagent fairlight track show INDEX`

## Search terms

- show Fairlight track
- reveal hidden audio track
- make A2 visible again
- unhide audio lane
- restore concealed Fairlight track
- track visibility on
- bring back waveform track
- display hidden dialogue track
- reopen audio lane in timeline
- make track row appear
- show audio without changing mute
- restore Fairlight timeline layout

## What it does

Show a Fairlight audio track.

## Do not use when

Use `fairlight unmute` when the track is visible but inaudible because it is muted. Unmute changes audible state; show is supposed to change layout visibility only.
Use the track enable command when a disabled track should resume processing/playback. A disabled track is not necessarily hidden.
Use `fairlight track folder` only if the “missing” tracks are inside a collapsed DaVinci Resolve 21 folder. Folder collapse and individual track visibility are separate GUI states, and folder management is also not exposed by CutAgent CLI.
Height readback cannot prove visibility.
The original track and clips may still exist; reveal it manually in DaVinci Resolve rather than introducing duplicate audio.

## Preflight and readback

Before choosing show, run `fairlight tracks` to confirm the audio track still exists and inspect its enabled/mute-related state. In the GUI, check whether it is individually hidden, inside a collapsed folder, filtered by workspace layout, or simply vertically out of view. This command cannot distinguish those cases.
After manually showing the track, verify the row appears in the Fairlight timeline and that mute/enable state did not change. There is no CLI visibility getter, so visual inspection is the only direct proof of the unhide operation.

## Public arguments and options

- `INDEX` (required) — Audio track index to show

## Boundaries and gotchas

- It exists so an agent does not “show” a track by enabling or unmuting it.
- It does not query current visibility.
- A missing app, project, timeline or positive-but-nonexistent index does not change the result.
- A manual reveal can depend on the current Fairlight workspace/layout; the CLI blocker does not distinguish per-page visibility from other UI filtering.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight track show --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
