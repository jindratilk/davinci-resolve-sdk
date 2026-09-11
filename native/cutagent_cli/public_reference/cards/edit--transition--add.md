# `edit transition add`

Syntax: `cutagent edit transition add TRANSITION_TYPE [DURATION] [--at VALUE] [--clip VALUE] [--placement VALUE] [--scope VALUE]`

## Search terms

- add cross dissolve
- put transition on clip start or end
- add video transition at edit
- add linked audio crossfade
- add Smooth Cut inside clip
- apply Zoom In transition
- add Rotate 90 Fusion transition
- place transition on both clip edges
- crossfade linked video and audio
- center transition at timeline frame

## What it does

Add a transition.

## Do not use when

Use `edit transition batch` for multiple targets and idempotent already-exists skipping; single add deliberately permits duplicate rows. Use clip fades/Fairlight fade commands for a fade to silence rather than a transition between items.
Do not pass `default` despite the help wording—it is not a supported key. Do not use on cloud/PostgreSQL, unsaved/default or ambiguous project databases, or without real post-reopen GUI/render proof.

## Preflight and readback

Choose an explicit supported transition, scope, placement and `12f`-style duration; avoid bare numeric duration ambiguity. For linked requests, inspect the resolved video/audio refs and confirm real linkage rather than same-name coincidence.
Afterward, require the intended project/timeline—not `Untitled Project`—to reopen. Inspect transition name/type, track, alignment, exact start/duration and actual adjacent edit; verify any audio companion and Smooth Cut split. Play/render through the seam and inspect handles, audio level curve, Fusion template and clip state.

## Public arguments and options

- `TRANSITION_TYPE` (required) — Transition type (default, cross-dissolve, etc.)
- `DURATION` (optional) — Transition duration (default: 24f, e.g. 12f, 0.5s, 00:00:00:12)
- `--at` (optional) — Record-domain position where transition is applied
- `--clip` (optional) — Target clip name for deterministic selection
- `--placement` (optional, default: `"both"`) — Placement: start|end|both
- `--scope` (optional, default: `"auto"`) — Transition scope: auto|linked|video|audio

## Boundaries and gotchas

- Explicit duration is only required to be positive.
- With placement start/end, at selects but does not relocate the row away from that clip edge.
- The centered ordinary path accepts `at` anywhere inside or exactly on the selected clip boundary; it does not require an existing edit seam.
- Start/end ordinary placement likewise does not prove an adjacent clip or compatible handles.
- Auto scope maps Cross Dissolve and Smooth Cut to linked, audio crossfades to audio, and Rotate 90/Zoom In to video.
- Cross Dissolve auto scope degrades to video-only when no heuristic audio match exists; explicit linked scope requires audio and can error.
- For other video transitions, linked scope does not create an audio transition.
- For Smooth Cut it can split linked audio but still inserts only the video Smooth Cut.
- The command does not independently validate every right-half metadata relationship.
- Re-running identical start/duration/type creates duplicate transition rows; only batch mode performs idempotent skips.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent edit transition add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
