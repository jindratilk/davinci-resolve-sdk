# `fairlight fade-out batch`

Syntax: `cutagent fairlight fade-out batch [--duration VALUE] [--timeline VALUE] [--item-id VALUE] [--track-index VALUE] [--start-frame VALUE] [--end-frame VALUE] [--input VALUE] [--skip-last-segment] [--skip-adjacent-same-track] [--clamp-half-clip] [--db VALUE] [--allow-empty]`

## Search terms

- batch audio fade out
- fade down multiple clips
- soften ends of dialogue clips
- remove clicks at clip endings
- add tail fades to audio items
- bulk Fairlight fade-out
- fade selected audio range endings
- ramp out every isolated segment
- fade clip tails and preserve gain
- clamp tail fade to half clip
- skip fades at contiguous edits

## What it does

Apply audio fade-out to many audio items.

## Do not use when

Do not use a clip-tail fade when the real request is a master/bus fade or a crossfade between edit points; use the owning Fairlight command. Use `fairlight audio-gain batch` for static level changes. A wide record range matches overlaps, not only contained clips.

## Preflight and readback

Before use, inventory exact audio items, IDs, tracks, ranges, adjacency, and current effects; checkpoint important Disk projects. Calculate whether default adjacency/last-segment rules will intentionally skip targets and whether half-duration clamping changes the request. For high-stakes delivery, confirm the visible tail handle or compare known-level render windows near the middle and final samples.

## Public arguments and options

- `--duration` (optional) — Fade duration, e.g. 0.2s or 12f
- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--item-id` (optional, repeatable)
- `--track-index` (optional) — Audio track index for range selectors
- `--start-frame` (optional) — Record-domain range start
- `--end-frame` (optional) — Record-domain range end
- `--input/--batch` (optional) — JSON batch file path
- `--skip-last-segment/--no-skip-last-segment` (optional, default: `false`) — Skip items at the latest selected end frame
- `--skip-adjacent-same-track/--no-skip-adjacent-same-track` (optional, default: `true`) — Skip items that touch a following selected item on the same track
- `--clamp-half-clip/--no-clamp-half-clip` (optional, default: `true`) — Clamp fade length to at most half of each clip duration
- `--db` (optional) — Optional audio gain in dB to merge with the fade effect chain
- `--allow-empty` (optional, default: `false`) — Do not fail when selectors match no items

## Boundaries and gotchas

- Default `--skip-adjacent-same-track` skips the earlier/left clip at an exact selected edit point.
- Adjacency is calculated only among selected targets.
- Touching unselected neighbors do not participate.
- `--skip-last-segment` compares against the maximum selected item end globally, not per track; every item ending at that maximum is skipped.
- Record range selectors use overlap and accept relative frame/time references.
- Duplicate targets from overlapping selectors are deduplicated by ID, with the first matched entry's requested fade length winning.
- It does not normalize duration/time, resolve the target timeline, test track bounds, or identify adjacency.
- `--timeline` changes the active timeline and the command does not restore the previously active one.
- Ambiguous compound shapes fail closed.

## Examples

- `cutagent fairlight fade-out batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
