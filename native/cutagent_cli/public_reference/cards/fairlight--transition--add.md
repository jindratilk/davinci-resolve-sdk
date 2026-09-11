# `fairlight transition add`

Syntax: `cutagent fairlight transition add TRANSITION_TYPE [DURATION] [--at VALUE] [--clip VALUE] [--placement VALUE]`

## Search terms

- add Fairlight audio transition
- add audio crossfade
- crossfade one audio clip
- fade both ends of an audio clip
- equal power audio crossfade
- constant gain audio crossfade
- smooth an audio edit
- blend audio across a cut
- center crossfade on timeline position
- put crossfade at clip start
- put crossfade at clip end
- add Cross Fade 0DB transition object

## What it does

Add a Fairlight audio transition object.

## Do not use when

Use `edit transition add` for video transitions, linked video-and-audio transition workflows, Smooth Cut, Fusion transitions, zoom/rotate transitions, or any request whose visible transition must be attached to a video track. `fairlight transition add cross-dissolve` is deliberately audio-only and becomes `Cross Fade 0DB`; it never inserts the video `Cross Dissolve` object.
Use `fairlight crossfade batch` when the request is to place crossfades across many edits or clips in one planned operation. This command resolves exactly one audio timeline item and adds only the positions implied by `--placement`.
For one target clip, `--placement start` or `end` here creates a transition object, but it is not a batch selector and does not find every eligible clip.
Do not use this command for Fairlight automation curves, clip keyframes, mixer fader rides, sidechain ducking, or a custom fade shape.
Do not use `--placement both --at CUT` when the intended result is separate fades at both clip boundaries. Omit `--at` to create start and end objects.
Do not use a transition to repair an unwanted gap or create source handles. Fix clip placement/handles first with the relevant Fairlight clip move, trim, slip, or nudge command.

## Preflight and readback

Before mutation, run `timeline items list --track-type audio` or the narrow Fairlight clip inventory and identify the exact clip name, track, start, end, and duration. When names repeat, choose a record-domain `--at` that lies inside only the intended copy. Confirm the active timeline frame rate because seconds and timecode are converted to frames.
Decide whether the request means a boundary fade or a centered seam transition. For a boundary fade, use `start`, `end`, or `both` without `--at`. For a seam, specify `--at` and `--placement both`. Check that the explicit duration is sensible for the clip and available audio handles; only the omitted default is automatically clamped.
Then open the Edit or Fairlight timeline at the target and visually confirm that DaVinci Resolve displays the crossfade on the intended clip boundary or seam. Audition or render through the transition to verify the selected curve sounds correct and that adequate handles exist. Re-list clip positions to confirm the command did not move or trim the audio item.

## Public arguments and options

- `TRANSITION_TYPE` (required) — Audio transition type: cross-fade-0db, cross-fade-3db, cross-fade+3db, or cross-dissolve
- `DURATION` (optional) — Transition duration (default: 24f, e.g. 12f, 0.5s, 00:00:00:12)
- `--at` (optional) — Record-domain position where the audio transition is applied
- `--clip` (optional) — Target audio clip name for deterministic selection
- `--placement` (optional, default: `"both"`) — Placement: start|end|both

## Boundaries and gotchas

- The name `cross-dissolve` is accepted only as an alias in this audio namespace.
- The additional aliases `crossfade` and `cross-fade` normalize to `cross-dissolve`, then follow the same audio-only `Cross Fade 0DB` path.
- `--placement both` has two different meanings.
- Without `--at`, it creates two rows at the clip start and end.
- With `--at`, it returns early from position planning and creates one centered row.
- `--at` is record-domain and is offset from the timeline's start timecode.
- Do not assume perfectly symmetric half-frame geometry.
- For centered placement, `--at` only has to be inside or exactly on the selected clip boundary.
- An explicit duration is only checked for being greater than zero; it is not clamped to the clip duration or available source handles.
- Exact repeated clip names are ambiguous without a position.
- With `--clip NAME --at FRAME`, the named item covering the frame must still be unique.
- Overlapping same-named items on multiple audio tracks remain ambiguous.
- With neither `--clip` nor `--at`, selection is video-led: the command gets the current video item and tries to match linked audio.
- Only `both` plus `--at` produces a centered-at-frame position.
- Inspect first and do not retry blindly after an uncertain response.
- The command does not create overlap, handles, or a neighboring clip.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight transition add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
