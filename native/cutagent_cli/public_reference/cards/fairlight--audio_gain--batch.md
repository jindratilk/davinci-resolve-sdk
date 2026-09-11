# `fairlight audio-gain batch`

Syntax: `cutagent fairlight audio-gain batch --db VALUE [--timeline VALUE] [--item-id VALUE] [--track-index VALUE] [--start-frame VALUE] [--end-frame VALUE] [--record-frame VALUE] [--record-duration VALUE] [--record-end VALUE] [--input VALUE] [--allow-empty] [--allow-multiple]`

## Search terms

- change clip gain on many audio clips
- batch audio gain
- bulk lower audio clips
- raise all clips in a range
- set fixed gain on selected audio items
- apply one gain value to multiple timeline clips
- make a group of clips quieter
- batch dialogue clip gain
- set gain for audio clips overlapping a time range
- archive-backed clip gain batch

## What it does

Adjust gain on multiple audio clips.

## Do not use when

Use `clip audio-gain` for one deterministically selected/linked clip rather than constructing a batch selector. Use track-level fader commands when the user means the mixer channel, bus-level commands for Main/FlexBus level, and automation commands for a gain curve that changes over time.
Do not use a broad time range when the user named particular clips. Resolve exact item IDs first. Do not use this route on cloud/PostgreSQL project libraries or when project close/reopen is unacceptable.

## Preflight and readback

Checkpoint the project independently and choose whether a range is intentionally allowed to match multiple clips. Validate the range in record-domain coordinates and remember that overlap, not containment, is used.
Afterward, require the same project and target timeline—not `Untitled Project`—to reopen. If `--timeline` was used, deliberately switch back to the editor's prior timeline when the workflow is finished.

## Public arguments and options

- `--db` (required) — Audio gain in dB
- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--item-id` (optional, repeatable)
- `--track-index` (optional) — Audio track index for time selectors
- `--start-frame` (optional) — Record-domain range start
- `--end-frame` (optional) — Record-domain range end
- `--record-frame` (optional) — Record-domain point or range start
- `--record-duration` (optional) — Duration from --record-frame
- `--record-end` (optional) — Record-domain range end from --record-frame
- `--input/--batch` (optional) — JSON batch file path
- `--allow-empty` (optional, default: `false`) — Do not fail when selectors match no items
- `--allow-multiple` (optional, default: `false`) — Allow one selector to update multiple items

## Boundaries and gotchas

- It cannot be combined in the same entry with track/time fields.
- Durations must resolve to more than zero frames, and every range end must be after its start.
- Range matching is any overlap.
- Without `--allow-multiple`, any one selector matching more than one item fails the entire batch.
- Multiple separate one-item selectors do not require that flag.
- `--allow-empty` suppresses a no-match failure per selector.
- `--allow-multiple` does not mean “all clips on the timeline.” It only permits every match from the supplied selector.
- The merge reconstructs all recognized gain, pan and fade entries, not only the requested gain bytes.
- It does not verify untargeted rows, GUI recognition, plugin availability or rendered level.
- Item IDs are accepted only when the row is an audio clip owned by an audio track in the target timeline.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight audio-gain batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
