# `bulk select`

Syntax: `cutagent bulk select [--track-type VALUE] [--track VALUE] [--name VALUE] [--name-starts-with VALUE] [--name-contains VALUE] [--name-regex VALUE] [--duration VALUE] [--min-duration VALUE] [--max-duration VALUE] [--from VALUE] [--to VALUE] [--clip-color VALUE] [--state VALUE] [--limit VALUE]`

## Search terms

- preview clips matching filters
- find timeline items in bulk
- list disabled timeline clips
- find clips overlapping record range
- search timeline names with regex
- inspect clips by color
- count matching timeline items
- preflight bulk edit targets

## What it does

Preview clips matched by a bulk selector.

## Do not use when

Use `timeline track items` when full source offsets, Media Pool identity/path, or every item on one known track is needed. Use the matching bulk mutation only after this preview exactly identifies intended timeline occurrences.

## Preflight and readback

No post-mutation readback is needed for this read-only command, but compare it with the mutation's returned IDs.

## Public arguments and options

- `--track-type` (optional, default: `"video"`) — Track type to search: video, audio, subtitle, or all.
- `--track` (optional) — Only clips on this 1-based track index.
- `--name` (optional) — Exact clip name match.
- `--name-starts-with` (optional) — Clip name prefix match (case-sensitive).
- `--name-contains` (optional) — Clip name substring match (case-insensitive).
- `--name-regex` (optional) — Clip name regular expression match.
- `--duration` (optional) — Exact clip duration: seconds ('4' / '4s'), frames ('96f'), or timecode.
- `--min-duration` (optional) — Minimum clip duration (same formats as --duration).
- `--max-duration` (optional) — Maximum clip duration (same formats as --duration).
- `--from` (optional) — Only clips overlapping a record-domain range start (timecode, seconds, frames).
- `--to` (optional) — Only clips overlapping a record-domain range end (timecode, seconds, frames).
- `--clip-color` (optional) — Only clips currently flagged with this clip color.
- `--state` (optional) — Only clips in this state: enabled or disabled.
- `--limit` (optional, default: `500`) — Safety cap on selected clips.

## Boundaries and gotchas

- With no selector flags, the default searches all items on all video tracks, not the whole timeline; default `--track-type` is `video` and limit is 500.
- `--from`/`--to` are offsets from the active timeline start, despite result timecodes being absolute.
- Range matching is half-open overlap: items ending exactly at `--from` or starting exactly at `--to` are excluded.
- A single `--track 1` with `--track-type all` means V1, A1, and ST1 where each exists; it is not a globally numbered track.
- `--limit` is a safety cap, not pagination.
- Ordering across `--track-type all` is video, then audio, then subtitle—not global chronological order.

## Examples

- `cutagent bulk select --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
