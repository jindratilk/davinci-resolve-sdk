# `bulk enable`

Syntax: `cutagent bulk enable [--track-type VALUE] [--track VALUE] [--name VALUE] [--name-starts-with VALUE] [--name-contains VALUE] [--name-regex VALUE] [--duration VALUE] [--min-duration VALUE] [--max-duration VALUE] [--from VALUE] [--to VALUE] [--clip-color VALUE] [--state VALUE] [--limit VALUE] [--fail-fast]`

## Search terms

- enable disabled timeline clips
- turn clips back on in bulk
- reactivate matching edits
- restore disabled b-roll
- batch set clip enabled true
- unhide timeline items without moving them
- enable clips by range or color
- re-enable selected occurrences

## What it does

Enable clips in bulk.

## Do not use when

Use `bulk disable` to bypass items. Enabling an item cannot make missing proxy/full-resolution media online.

## Preflight and readback

After enabling, run the identical identity filters with `--state enabled`, compare item IDs/ranges, and inspect output where layers overlap. If only some disabled clips should return, filter by ID-equivalent track/name/range evidence rather than broad names.

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
- `--fail-fast` (optional, default: `false`) — Stop at the first failing clip instead of continuing.

## Boundaries and gotchas

- Linked audio/video occurrences may require separate matches; the command does not traverse link relationships.
- Use `--state disabled` and at least one identity/range filter when restoration scope matters.
- `--fail-fast` stops processing only; it is not transactional.

## Examples

- `cutagent bulk enable --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
