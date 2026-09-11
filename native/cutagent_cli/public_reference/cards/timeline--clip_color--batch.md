# `timeline clip-color batch`

Syntax: `cutagent timeline clip-color batch --batch VALUE [--timeline-name VALUE] [--track-type VALUE] [--track VALUE] [--all-tracks] [--require-count-match] [--allow-partial]`

## Search terms

- batch timeline clip colors
- set clip color by frame bounds
- clear clip colors
- annotate timeline segments
- exact clip range matching
- color video and audio items
- clip color preflight
- batch editorial labels
- timeline segment colors

## What it does

Update timeline clip colors.

## Do not use when

Do not use this command with approximate times, clip names, source-time bounds, or transition-inclusive ranges.
Do not scan synchronized video/audio scopes with identical bounds unless ambiguity is resolved; duplicate detection ignores track identity and rejects repeated bound pairs.
Do not use partial mode when atomic all-or-nothing behavior is required.

## Preflight and readback

Use a checkpoint for broad edits.
Run connected dry-run and require a reviewed preflight: expected/actual counts, missing/extra bounds, duplicates, matched count, current colors, and readiness.
Re-enumerate timeline items and manually restore from preflight current colors if any failure or wrong target occurred.

## Public arguments and options

- `--batch` (required) — Batch JSON path
- `--timeline-name/--timeline` (optional) — Target timeline name; defaults to active timeline
- `--track-type` (optional, default: `"video"`) — Track type: video, audio, or all
- `--track/--track-index` (optional, default: `1`) — Track index when not using --all-tracks
- `--all-tracks` (optional, default: `false`) — Scan all tracks for the selected track type
- `--require-count-match/--no-require-count-match` (optional, default: `true`) — Require expected and actual item counts to match before mutation
- `--allow-partial/--no-allow-partial` (optional, default: `false`) — Apply only matched bounds when preflight has non-duplicate mismatches

## Boundaries and gotchas

- Exact help is `cutagent timeline clip-color batch --batch PATH`.
- The batch input is file-only; there is no inline JSON option.
- Every entry must be an object.
- Case-insensitive clear aliases are empty string, `clear`, `none`, `default`, and `null`.
- Frame and millisecond bounds cannot be mixed in one entry.
- Both start and end are required.
- End must be greater than start.
- Frame values must parse as integers; seconds/timecode strings are not supported.
- Millisecond parsing accepts floats but does not explicitly reject non-finite values before rounding.
- Track type must be `video`, `audio`, or `all`.
- Default scope is video track 1.
- `--all-tracks` scans every existing track of the selected type(s) and effectively ignores the provided track index.
- An unavailable track type with count zero is not rejected as out of range; it contributes no items.
- Duplicate expected bounds are always rejected.
- Duplicate actual bounds are always rejected, including identical synchronized items on different tracks.
- Default `--require-count-match` compares batch entry count with every actual item in the selected scope.
- A valid subset edit normally needs `--no-require-count-match`.
- `--allow-partial` can bypass non-duplicate missing/count preflight and apply matched entries only.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline clip-color batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
