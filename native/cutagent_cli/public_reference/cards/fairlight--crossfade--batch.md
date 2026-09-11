# `fairlight crossfade batch`

Syntax: `cutagent fairlight crossfade batch [--duration VALUE] [--timeline VALUE] [--item-id VALUE] [--track-index VALUE] [--start-frame VALUE] [--end-frame VALUE] [--input VALUE] [--clamp-half-clip] [--allow-empty]`

## Search terms

- crossfade adjacent audio clips
- smooth audio edit point
- fade out one clip and fade in next
- remove click at dialogue cut
- soften hard audio cut
- batch audio edit fades
- add fades around audio cuts
- Fairlight crossfade multiple clips
- dip audio across edit point
- paired fade-out fade-in
- crossfade contiguous dialogue segments
- fade both sides of an audio edit

## What it does

Apply crossfades to adjacent audio edit points.

## Do not use when

`fairlight crossfade batch` only pairs two clip-edge fades and can create an audible dip.
Use `fairlight fade-in batch` when only clip heads need fades and `fairlight fade-out batch` when only tails need fades.
Do not use it to repair a gap or overlap. Move/trim the items intentionally first.
Do not use one item ID when expecting the command to discover its unselected neighbor. Both item rows must be selected. Prefer a narrow range spanning both sides or pass both IDs.
Do not use it for video transitions, bus automation, track fades, crossfades between different tracks, or crossfades between layers on the same time range. Pairing occurs only within one track's selected serial order.

## Preflight and readback

Choose duration per edge, not as a total overlap length.

## Public arguments and options

- `--duration` (optional) — Crossfade duration, e.g. 0.2s or 12f
- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--item-id` (optional, repeatable)
- `--track-index` (optional) — Audio track index for range selectors
- `--start-frame` (optional) — Record-domain range start
- `--end-frame` (optional) — Record-domain range end
- `--input/--batch` (optional) — JSON batch file path
- `--clamp-half-clip/--no-clamp-half-clip` (optional, default: `true`) — Clamp each crossfade edge to at most half of its clip duration
- `--allow-empty` (optional, default: `false`) — Do not fail when selectors match no adjacent edit points

## Boundaries and gotchas

- Pairing considers only selected targets.
- A range selector matches every item that overlaps the range, not only items fully contained in it.
- The range should be narrow enough to avoid unintended additional pairs.
- Default `--clamp-half-clip` floors half-duration to an integer.
- Duration is required globally unless each input-file entry supplies one of the accepted per-entry fade/crossfade duration fields.
- Frame and time-reference duration fields cannot both appear in one entry.
- The CLI has no inline `--batch-json` option.
- Dry-run does not switch or verify that named timeline.

## DaVinci Resolve editions

Free was not independently exercised for this card.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight crossfade batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
