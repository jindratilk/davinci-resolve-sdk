# `bulk clip-color-set`

Syntax: `cutagent bulk clip-color-set COLOR [--track-type VALUE] [--track VALUE] [--name VALUE] [--name-starts-with VALUE] [--name-contains VALUE] [--name-regex VALUE] [--duration VALUE] [--min-duration VALUE] [--max-duration VALUE] [--from VALUE] [--to VALUE] [--clip-color VALUE] [--state VALUE] [--limit VALUE] [--fail-fast]`

## Search terms

- color code timeline clips in bulk
- set clip color on matching edits
- clear timeline item colors
- mark all b-roll clips orange
- recolor clips by track and range
- tag disabled edits with clip color
- batch set timeline clip color
- remove clip color from selected occurrences

## What it does

Set clip colors in bulk.

## Do not use when

Use `media color set/clear` to change a Media Pool object's color, and `clip flag`/`media flag` for flags rather than the single clip-color field. Use the single-clip color command when one already-disambiguated current occurrence is intended. Do not use color as a durable content taxonomy if edits may be recreated from the Media Pool; this mutation belongs to timeline items.

## Preflight and readback

Record existing colors so each row can be restored; narrow by track/range when duplicate names exist. After clearing, verify those IDs no longer match any prior color and inspect the timeline UI if color semantics drive editorial workflow.

## Public arguments and options

- `COLOR` (required) — Clip color name (e.g. Orange, Teal) or 'clear' to remove
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

- The `--clip-color` selector is evaluated before mutation.
- Clearing only the blue item left the red item Orange, proving the color is per occurrence rather than shared through the two Media Pool sources.
- `--fail-fast` stops at the first failure but does not roll back colors already applied earlier in timeline order.

## Examples

- `cutagent bulk clip-color-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
