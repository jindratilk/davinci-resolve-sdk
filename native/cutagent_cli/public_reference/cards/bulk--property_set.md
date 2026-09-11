# `bulk property-set`

Syntax: `cutagent bulk property-set KEY VALUE [--track-type VALUE] [--track VALUE] [--name VALUE] [--name-starts-with VALUE] [--name-contains VALUE] [--name-regex VALUE] [--duration VALUE] [--min-duration VALUE] [--max-duration VALUE] [--from VALUE] [--to VALUE] [--clip-color VALUE] [--state VALUE] [--limit VALUE] [--fail-fast]`

## Search terms

- set transform on multiple clips
- batch change timeline item property
- set opacity across matching edits
- zoom all selected clips
- change Pan or ZoomX in bulk
- apply numeric property to timeline occurrences
- batch toggle clip property boolean
- set same Inspector value on many clips

## What it does

Change clip properties in bulk.

## Do not use when

Use `clip transform` or the single `clip properties` setter for one disambiguated occurrence or when typed domain-specific validation is needed. Use color/Fairlight/Fusion-specific commands for node inputs, grades, effects, or mix parameters that are not TimelineItem properties.

## Preflight and readback

Confirm key spelling/case and accepted type on one disposable item before applying widely. Restore originals per item if the batch unintentionally homogenized them.

## Public arguments and options

- `KEY` (required) — Timeline item property key (e.g. ZoomX, Pan, Opacity)
- `VALUE` (required) — Property value; numbers and true/false are auto-typed
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

- Property keys are unconstrained and case-sensitive according to DaVinci Resolve.
- Numeric-looking text cannot be forced to remain a string through this command.
- This command does not inspect or remove keyframes explicitly; verify animation after use.
- `--track-type all` with a video-specific key can create mixed success/failure rows.
- `--fail-fast` does not restore properties changed before the first failure.

## Examples

- `cutagent bulk property-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
