# `fairlight fade-in batch`

Syntax: `cutagent fairlight fade-in batch [--duration VALUE] [--timeline VALUE] [--item-id VALUE] [--track-index VALUE] [--start-frame VALUE] [--end-frame VALUE] [--input VALUE] [--skip-first-segment] [--skip-adjacent-same-track] [--clamp-half-clip] [--db VALUE] [--allow-empty]`

## Search terms

- batch audio fade in
- fade up multiple clips
- soften starts of dialogue clips
- remove clicks at clip beginnings
- add head fades to audio items
- bulk Fairlight fade-in
- fade selected audio range
- ramp in every isolated segment
- fade clip starts and preserve gain
- clamp fade to half clip
- skip fades at contiguous edits

## What it does

Apply audio fade-in to many audio items.

## Do not use when

Use `fairlight crossfade batch` only when both sides of adjacent edit points should be paired; this command's default adjacency rule intentionally leaves the right-hand clip without a fade-in. Do not use this for track/bus automation or a timeline master fade.

## Preflight and readback

Use an isolated/checkpointed Disk project and calculate the effective half-clip clamp.

## Public arguments and options

- `--duration` (optional) — Fade duration, e.g. 0.2s or 12f
- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--item-id` (optional, repeatable)
- `--track-index` (optional) — Audio track index for range selectors
- `--start-frame` (optional) — Record-domain range start
- `--end-frame` (optional) — Record-domain range end
- `--input/--batch` (optional) — JSON batch file path
- `--skip-first-segment/--no-skip-first-segment` (optional, default: `false`) — Skip items at the earliest selected start frame
- `--skip-adjacent-same-track/--no-skip-adjacent-same-track` (optional, default: `true`) — Skip items that touch a previous selected item on the same track
- `--clamp-half-clip/--no-clamp-half-clip` (optional, default: `true`) — Clamp fade length to at most half of each clip duration
- `--db` (optional) — Optional audio gain in dB to merge with the fade effect chain
- `--allow-empty` (optional, default: `false`) — Do not fail when selectors match no items

## Boundaries and gotchas

- Default `--skip-adjacent-same-track` skips the later/right clip at an exact selected edit point.
- Adjacency is calculated only among selected targets.
- If the neighboring clip is outside the selectors, it cannot cause a skip even when it touches the selected clip in the timeline.
- `--skip-first-segment` uses the minimum start across all selected tracks, not the first item independently on each track; simultaneous earliest items are all skipped.
- Duration is required globally unless every JSON entry has an edge-specific/general duration field.
- `--timeline` switches the active timeline before mutation and does not restore the previously active timeline.

## Examples

- `cutagent fairlight fade-in batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
