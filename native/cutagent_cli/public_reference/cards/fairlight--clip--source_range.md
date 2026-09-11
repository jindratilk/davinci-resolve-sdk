# `fairlight clip source-range`

Syntax: `cutagent fairlight clip source-range [CLIP]`

## Search terms

- inspect audio clip source range
- show source in and out
- check left right source handles
- get Fairlight clip offsets
- see available audio before after edit
- verify clip slip source offset
- check trim handles on audio clip
- inspect timeline versus source bounds
- determine whether clip can extend
- preflight Fairlight slip or trim

## What it does

Check source range information for a Fairlight timeline clip.

## Do not use when

Use `fairlight clip slip` to change source In while preserving record range, or `fairlight clip trim` to change an edit edge. This reader only provides pre/post evidence.
Use `fairlight clip info` for broad TimelineItem properties, `track-info` for track/index and `channel-map clip` for audio channel selection. Source range does not include item ID, track binding, gain, pan or channel mapping.
Use Media Pool readers when the question concerns the full source asset independently of a timeline occurrence. Offsets and record bounds here belong to one TimelineItem.
The command neither reports ambiguity nor reveals resolved item ID/track; choose a unique TimelineItem name from a prior inventory.

## Preflight and readback

Before reading, identify the exact occurrence by unique name, track and record bounds. If relying on omission, check playhead/current-video state. For a slip/trim preflight, retain all returned keys and distinguish missing values from numeric zero.
Afterward, compare record `start/end/duration` with the intended item inventory. Interpret left/right offsets alongside the actual media type and source-bound operation.

## Public arguments and options

- `CLIP` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- The command name says source range, but `start`, `end` and `duration` are TimelineItem record-domain values.
- Explicit matching accepts source/Media Pool aliases and case-insensitive basenames; first match wins and duplicates are not rejected.
- Dry-run does not connect, resolve the selector, inspect getter availability or return any range values.

## DaVinci Resolve editions

Getter availability and offset semantics can vary in other versions and Free.

## Examples

- `cutagent fairlight clip source-range --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
