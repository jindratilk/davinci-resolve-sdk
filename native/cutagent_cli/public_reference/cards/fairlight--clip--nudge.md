# `fairlight clip nudge`

Syntax: `cutagent fairlight clip nudge [--timeline VALUE] [--item-id VALUE] [--track VALUE] [--start-frame VALUE] [--current-end-frame VALUE] [--name VALUE] [--delta VALUE] [--allow-overlap] [--allow-linked-audio-only] [--include-linked-video]`

## Search terms

- nudge audio clip by frames
- shift Fairlight clip earlier
- shift Fairlight clip later
- move dialogue a few frames
- correct audio sync offset
- delay audio clip
- advance audio clip
- offset timeline sound by seconds
- move audio left or right on timeline
- Fairlight relative clip move
- push audio 6 frames
- pull audio back 100 milliseconds

## What it does

Adjust Fairlight audio clip timing.

## Do not use when

`clip nudge` cannot accept a destination track or absolute target.
Use trim or slip when the record position must remain fixed and the clip edge/source content should change. Nudge preserves duration and source in/out.
Use ripple-edit operations when later material should follow the shift.
Do not use this command for a multi-clip selection, arbitrary linked group, layer, or cross-track collision resolution. Calculate and verify each target or choose a group-aware workflow.
Use `--allow-linked-audio-only` only for an intentional audio-only desynchronization.

## Preflight and readback

Before nudging, inventory the exact item ID, audio track, absolute start/end/duration, name aliases, source range, neighbors/transitions and link state. Calculate the signed delta with the exact timeline rate and confirm the proposed new range. Use item ID when available.
For public operation, prove companion membership from DaVinci Resolve's reported link relationship and bind every companion to one stable exact item identity; do not infer links from coincident ranges or names. After reopen, mandatory verification checks requested bounds, link membership, and unchanged surrounding items. Required verification must succeed; otherwise the operation is automatically rolled back to the prior project state. If automatic recovery cannot complete, JSON identifies possible mutation and required manual recovery.
Confirm the old range, neighboring clips, duration, track and source range. Isolate and audition or render the changed range; structural readback does not prove audible sync or waveform content.

## Public arguments and options

- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--item-id` (optional)
- `--track/--track-index` (optional, default: `1`) — Audio track index for selector
- `--start-frame` (optional) — Current audio item start in record-domain frames/time
- `--current-end-frame` (optional) — Current audio item end for stricter selection
- `--name` (optional) — Current timeline item name for stricter selection
- `--delta/--nudge/--by` (optional) — Signed nudge amount, e.g. 12f or -0.5s
- `--allow-overlap` (optional, default: `false`) — Allow the nudged audio item to overlap another item on the same track
- `--allow-linked-audio-only` (optional, default: `false`)
- `--include-linked-video` (optional, default: `false`)

## Boundaries and gotchas

- Delta is mandatory even in dry-run.
- A valid zero delta such as `0f` does not edit the item and reports the unchanged state.
- Empty and sign-only values remain invalid.
- For a negative value beginning with `-`, `--by=-6f` avoids CLI option parsing ambiguity.
- Without item ID, selection requires `--start-frame` or `--name` on the specified 1-based audio track.
- `--current-end-frame` and case-insensitive display/source aliases only narrow the match; multiple matches fail.
- With item ID, `--start-frame`, `--current-end-frame` and `--name` are mutually exclusive.
- Without `--allow-overlap`, any positive intersection on the destination range blocks the nudge.
- Fairlight transition rows touching the old or new range block the edit even with overlap allowed.
- Use `clip move` if track binding must change.
- `--include-linked-video` applies the same delta to the exact video rows; linked non-video/complex companion groups fail closed.
- It does not prove audible sync or waveform content.
- Explicit `--timeline` switches to that timeline and leaves it active after reopen.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight clip nudge --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
