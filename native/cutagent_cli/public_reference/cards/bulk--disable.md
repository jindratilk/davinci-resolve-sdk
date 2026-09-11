# `bulk disable`

Syntax: `cutagent bulk disable [--track-type VALUE] [--track VALUE] [--name VALUE] [--name-starts-with VALUE] [--name-contains VALUE] [--name-regex VALUE] [--duration VALUE] [--min-duration VALUE] [--max-duration VALUE] [--from VALUE] [--to VALUE] [--clip-color VALUE] [--state VALUE] [--limit VALUE] [--fail-fast]`

## Search terms

- disable matching timeline clips
- turn off clips in bulk
- mute selected video occurrences
- bypass multiple timeline items
- deactivate b-roll clips
- disable edits by range or name
- batch set clip enabled false
- hide matching clips without deleting

## What it does

Disable clips in bulk.

## Do not use when

Use `bulk enable` to reverse disabled occurrences. Use track enable/mute controls when an entire track should be bypassed as a unit, and audio mute/fairlight controls when the request concerns mix state rather than item enablement. Use delete/ripple commands when the items and gaps must actually be removed.

## Preflight and readback

After the command, use the same selector plus `--state disabled` and confirm every expected ID, then inspect viewer/audio output at representative overlaps. Preserve a list for `bulk enable` restoration.

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

- `--state` filters pre-state.
- Default selector covers video only and can match up to 500 items.
- No visible GUI selection is required.
- It only shortens the results list at the first rejected item.
- Disabled items remain selectable by duration/name/range and can still affect editorial operations that inspect timeline structure.

## Examples

- `cutagent bulk disable --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
