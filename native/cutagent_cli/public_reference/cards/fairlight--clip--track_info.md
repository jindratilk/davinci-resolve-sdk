# `fairlight clip track-info`

Syntax: `cutagent fairlight clip track-info [CLIP]`

## Search terms

- which track is this audio clip on
- find clip audio track number
- get timeline item track binding
- locate sound clip in timeline
- audio clip track index
- is clip on A1 or A2
- identify clip track type
- find where dialogue clip is placed
- current clip track
- Fairlight clip location

## What it does

Check track type and index for a Fairlight timeline clip.

## Do not use when

Use `fairlight clip info` for item metadata such as start, end, duration, flags, markers and properties, or `fairlight clip source-range` for source handles and offsets. Track-info intentionally does not describe clip content or record/source range.
Use `timeline track list` when enumerating all tracks or mapping indices to track names. This command does not return the track's display name and cannot prove whether a returned index is enabled, locked, audible or routed.
Do not use a bare duplicated clip name when the exact occurrence matters. This command has no track, record-frame or item-ID selector and silently chooses the first matching item. First obtain a unique name/position or use a readback command with precise track-and-frame selectors.
Do not use this as proof that a named target is an audio item merely because it is under the Fairlight command group.

## Preflight and readback

Before querying by name, list the relevant timeline tracks/items and determine whether the label is unique across both video and audio. If it is not unique, use position-aware inventory to identify the intended occurrence rather than relying on scan order.
If the next command targets an audio track, cross-check the index against `timeline track list` or `fairlight tracks`, and use `timeline item-at`/clip inventory to prove that the intended occurrence is actually there.

## Public arguments and options

- `CLIP` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- Duplicate names are not reported as ambiguous.
- A basename or case-insensitive alias can match while the output echoes the alias.
- A playhead exactly at an item's end does not match because ranges are end-exclusive.
- The command does not independently prove the item appears in that track's item list.
- The output does not include track name, format, lock, enable, mute/solo, mixer state, bus routing, channel count or neighboring items.

## Examples

- `cutagent fairlight clip track-info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
