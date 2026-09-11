# `fairlight clip trim`

Syntax: `cutagent fairlight clip trim [--timeline VALUE] [--item-id VALUE] [--track VALUE] [--start-frame VALUE] [--current-end-frame VALUE] [--name VALUE] [--duration VALUE] [--end-frame VALUE] [--target-start-frame VALUE] [--head-delta VALUE] [--allow-overlap] [--no-source-bounds] [--allow-linked-audio-only] [--include-linked-video]`

## Search terms

- trim Fairlight audio clip
- shorten audio clip tail
- set audio clip duration
- move audio clip right edge
- cut off end of dialogue
- trim beginning of audio clip
- move audio clip left edge
- remove silence from clip head
- extend audio clip to the left
- extend audio clip to the right
- set clip end frame
- change audio edit point

## What it does

Runs the public `fairlight clip trim` CutAgent command.

## Do not use when

Use `fairlight clip slip` when the record start/end must remain fixed and only the source content underneath should change. A head trim changes record start and duration as well as source In; slip changes only source In.
Use `fairlight clip move` or `fairlight clip nudge` when both edges and the whole occurrence must shift together. Use `fairlight clip split` to create two timeline items at an interior edit point. Trim keeps one item and changes one edge.
Use a ripple-edit command when downstream items should close or open space. This command explicitly leaves neighboring clips in place and either creates a gap when shrinking or requires an explicit overlap when extending into occupied record space.
Do not use this route for transition-aware trims, selection/range trims, layer-aware trims, or linked non-video/complex groups.
Do not use `--no-source-bounds` merely to force an unexplained extension.

## Preflight and readback

Before mutation, capture the exact item ID, audio track, absolute record start/end/duration, source In, left/right offsets, neighboring item ranges, transitions, link group and time-map/retime state.
For public operation, prove companion membership from DaVinci Resolve's reported link relationship and bind every companion to one stable exact item identity; do not infer links from coincident ranges or names. After reopen, mandatory verification checks requested edge bounds, link membership, and unchanged surrounding items. Required verification must succeed; otherwise the operation is automatically rolled back to the prior project state. If automatic recovery cannot complete, JSON identifies possible mutation and required manual recovery.
In both cases re-check neighboring gaps/overlaps, links and transitions, then audition or render across the changed edge. For `--include-linked-video`, verify audio and video independently.

## Public arguments and options

- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--item-id` (optional)
- `--track/--track-index` (optional, default: `1`) — Audio track index for selector
- `--start-frame` (optional) — Current audio item start in record-domain frames/time
- `--current-end-frame` (optional) — Current audio item end for stricter selection
- `--name` (optional) — Current timeline item name for stricter selection
- `--duration` (optional) — New audio item duration: frames, seconds, or timecode
- `--end-frame/--target-end-frame` (optional) — New audio item end in record-domain frames/time
- `--target-start-frame/--new-start-frame` (optional) — New audio item head/start in record-domain frames/time
- `--head-delta/--trim-start-by` (optional) — Signed left-edge trim amount, e.g. 12f or -0.5s
- `--allow-overlap` (optional, default: `false`) — Allow the new duration to overlap the next item on the same audio track
- `--no-source-bounds` (optional, default: `false`) — Do not reject API-reported source/right-trim overrun before DB write
- `--allow-linked-audio-only` (optional, default: `false`)
- `--include-linked-video` (optional, default: `false`)

## Boundaries and gotchas

- `--duration` is a positive length.
- `--end-frame` and `--target-start-frame` are record-domain positions; `--head-delta` is a signed duration, not an absolute frame.
- Without item ID, at least start or name is required.
- Matches are limited to the stated 1-based audio track and must be unique; current end is strongly recommended because names and source aliases can repeat.
- With item ID, `--start-frame`, `--current-end-frame` and `--name` are mutually exclusive.
- `--no-source-bounds` bypasses that protection; it does not apply to the head's mandatory non-negative-In check.
- `--allow-overlap` affects record-range guards only.
- It does not make transition handling, source extent or linked sync safe.
- Head mode scans all other rows on the track for overlap against the resulting range.
- The command cannot reposition, rebind or verify a Fairlight crossfade/transition.
- `--allow-linked-audio-only` intentionally leaves video unchanged.
- `--allow-linked-audio-only` and `--include-linked-video` are mutually exclusive.
- Only simple/empty time maps are regenerated.
- It cannot prove waveform content or plugin continuity.
- Explicit `--timeline` switches to that timeline before the operation and leaves the reopened target timeline active.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight clip trim --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
