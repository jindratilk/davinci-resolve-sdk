# `clip fade-in`

Syntax: `cutagent clip fade-in [NAME] [--at VALUE] [--scope VALUE] [--edge VALUE] [--duration VALUE] [--video-duration VALUE] [--audio-duration VALUE]`

## Search terms

- fade clip in or out
- add video fade handles
- fade audio at both ends
- ramp sound from silence
- fade picture to black
- apply start end clip fade
- set different audio and video fade lengths
- add clip edge fades

## What it does

Apply fade-ins to linked clips.

## Do not use when

Use Fairlight fade batch commands when selecting multiple audio items or when decoded per-item fade verification is required. Use transitions/crossfades when blending adjacent clips rather than fading a single edge to/from silence/black. Do not use this command on non-Disk/cloud project libraries or assume `--scope audio` can target a pure audio-only timeline.

## Preflight and readback

Dry-run with explicit `--at`, scope, edge, and frame/second durations; review resolved frame counts. After mutation/reopen, require the intended timeline and IDs, inspect handles in Edit/Fairlight, render the affected edge(s), and compare waveform/pixels to baseline.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--at` (optional) — Record-domain position for deterministic clip selection
- `--scope` (optional, default: `"linked"`) — Fade scope: linked|video|audio
- `--edge` (optional, default: `"start"`) — Fade edge: start|end|both
- `--duration` (optional) — Fade duration for both video and audio (e.g. 12f, 0.5s)
- `--video-duration` (optional) — Override fade duration for video
- `--audio-duration` (optional) — Override fade duration for audio

## Boundaries and gotchas

- The command name is `fade-in`, but `--edge end` and `--edge both` also create fade-outs.
- Default 44-frame video fade exceeds many short clips; the command does not clamp durations to item length or half-length.

## Examples

- `cutagent clip fade-in --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
