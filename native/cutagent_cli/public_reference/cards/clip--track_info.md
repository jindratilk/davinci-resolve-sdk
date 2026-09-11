# `clip track-info`

Syntax: `cutagent clip track-info [CLIP]`

## Search terms

- which track is this clip on
- get video track index for item
- find audio track number
- identify timeline item track type
- locate named clip in timeline tracks
- current clip track readback
- verify item moved to another track

## What it does

Check the track details for a timeline item.

## Do not use when

Use `clip list` to enumerate all items on a known track, `timeline info` for track counts, and `clip linked list` to inspect counterparts. Do not use it to inspect Media Pool folders or source audio channel mapping.

## Preflight and readback

List the relevant timeline tracks to establish name uniqueness, or position the playhead when omitting the name. After moving/relinking an item, run this readback and then list the reported track to confirm its range/name there.

## Public arguments and options

- `CLIP` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- Track index is one-based.
- This command does not expose stacked layer order beyond the numeric index and does not state whether the track/item is enabled, locked, muted, or linked.

## Examples

- `cutagent clip track-info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
