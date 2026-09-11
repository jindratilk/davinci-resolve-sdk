# `edit remove-range`

Syntax: `cutagent edit remove-range --in VALUE --out VALUE [--track-type VALUE] [--track VALUE]`

## Search terms

- delete clips overlapping time range
- clear timeline interval
- remove all video items in range
- lift clips between in and out
- delete every clip touching selection
- clear V1 between timecodes
- remove audio clips across interval
- delete whole items intersecting range
- clear timeline section without ripple
- remove stacked clips by range
- empty track area between frames
- batch delete timeline items by time

## What it does

Remove all clips in a time range.

## Do not use when

Use trim/blade operations when only the material inside the interval should disappear while partial clips survive. Run separate, explicitly reviewed video and audio operations if both types truly need removal.
Do not use this command expecting an In/Out range delete like DaVinci Resolve's UI: a long clip touching the interval is removed in its entirety. Track 0 deliberately selects every overlap across the chosen track type.

## Preflight and readback

Before mutation, list every item whose `start < out && end > in` on the exact type/track scope, including long clips that merely cross a boundary. Check links, locks, transitions, effects and neighboring record positions, then checkpoint the timeline. Use a positive track index unless deletion across every track of that type is deliberate.
Afterward, inspect the returned stable targets and protected-state readback, then independently list every scoped track for high-value work. Confirm every intended item is absent, nonoverlapping items remain, no downstream timing shifted and linked counterpart tracks have the intended state. If any target remains or readback fails, stop rather than retrying the broad range blindly.

## Public arguments and options

- `--in` (required) — Range start
- `--out` (required) — Range end
- `--track-type` (optional, default: `"video"`) — Track type: video, audio
- `--track` (optional, default: `0`)

## Boundaries and gotchas

- This is whole-item deletion, not range trimming.
- Only `video` or `audio` is allowed.
- `--track 0` means all tracks of the chosen type.
- Item selection uses only those absolute half-open boundaries.
- Dry-run does not connect, parse frames, enumerate targets, inspect locks or show which clips would be removed; it is unsafe as the sole preview for this broad command.
- Returned targets include stable identity, track, record range, source range, and linked identities rather than relying on repeated names.
- A locked-track refusal or unchanged target fails readback and cannot be counted as a successful removal.
- Generators/titles or other timeline objects returned by the track list can be targeted even when their source semantics differ; no MediaPoolItem is required for deletion.

## Examples

- `cutagent edit remove-range --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
