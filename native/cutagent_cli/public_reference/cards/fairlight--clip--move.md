# `fairlight clip move`

Syntax: `cutagent fairlight clip move [--timeline VALUE] [--item-id VALUE] [--track VALUE] [--start-frame VALUE] [--current-end-frame VALUE] [--name VALUE] [--to-start-frame VALUE] [--delta VALUE] [--to-track VALUE] [--allow-overlap] [--allow-linked-audio-only] [--include-linked-video]`

## Search terms

- move audio clip on timeline
- reposition Fairlight clip
- nudge audio by frames
- move sound clip to another track
- change audio item start frame
- shift dialogue earlier or later
- move audio from A1 to A2
- correct sync offset on audio clip
- relocate timeline audio item
- set Fairlight clip record position
- move linked audio and video together
- non-ripple audio clip move

## What it does

Move and nudge a Fairlight audio item.

## Do not use when

Use ripple-edit commands when surrounding material should close/open time.
Use trim/slip/source-range commands when the record position must stay fixed and source in/out should change. Move preserves duration and source range.
Do not use this for multiple selected clips, non-simple link groups, cross-track collision resolution, layer moves or selection-range moves. Apply individually only after proving group semantics, or use a workflow designed for the group.
Do not pass `--allow-linked-audio-only` casually.

## Preflight and readback

Before mutation, identify the saved named Disk project, exact timeline, audio track, TimelineItem ID, name, absolute start/end/duration, aliases, links and neighboring clips/transitions on source and destination tracks. Prefer the exact item ID for identity.
For public operation, prove companion membership from DaVinci Resolve's reported link relationship and bind every companion to one stable exact item identity; do not infer links from coincident ranges or names. After reopen, mandatory verification checks requested bounds, link membership, and unchanged surrounding items. Required verification must succeed; otherwise the operation is automatically rolled back to the prior project state. If automatic recovery cannot complete, JSON identifies possible mutation and required manual recovery.
Confirm old range is empty, duration/source range is unchanged, neighbors did not move, intended A/V companion state is correct and the intended timeline reopened. Isolate and audition or render the changed range; structural readback does not prove audible sync or waveform content.

## Public arguments and options

- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--item-id` (optional)
- `--track/--track-index` (optional, default: `1`) — Audio track index for selector
- `--start-frame` (optional) — Current audio item start in record-domain frames/time
- `--current-end-frame` (optional) — Current audio item end for stricter selection
- `--name` (optional) — Current timeline item name for stricter selection
- `--to-start-frame/--to` (optional) — New audio item start in record-domain frames/time
- `--delta/--nudge` (optional) — Signed move amount, e.g. 12f or -0.5s
- `--to-track/--to-track-index` (optional) — Destination audio track index; may be combined with --to-start-frame or --delta
- `--allow-overlap` (optional, default: `false`) — Allow the moved audio item to overlap another item on the same track
- `--allow-linked-audio-only` (optional, default: `false`)
- `--include-linked-video` (optional, default: `false`)

## Boundaries and gotchas

- `--item-id` is mutually exclusive with `--start-frame`, `--current-end-frame` and `--name`.
- Without item ID, track index is 1-based and exact; at least start or name is required.
- Candidate name matching is case-insensitive across display/source aliases, and multiple matches are rejected.
- `--current-end-frame` is a selector for the old end, not a new end.
- `--to-start-frame` and `--delta` are mutually exclusive.
- A track-only move is allowed only when `--to-track` is present.
- `--allow-overlap` only bypasses clip collision rejection.
- It does not resolve, layer, crossfade or mix overlapping items.
- Transition rows touching the old or new range block the operation even with `--allow-overlap`; transitions must be removed/recreated.
- `--include-linked-video` does not implement arbitrary linked-group moves and does not move a video companion to another track.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight clip move --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
