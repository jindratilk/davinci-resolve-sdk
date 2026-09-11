# `timeline items delete`

Syntax: `cutagent timeline items delete [--timeline VALUE] [--track-type VALUE] [--track-index VALUE] [--start-frame VALUE] [--end-frame VALUE] [--match VALUE] [--allow-empty] [--force]`

## Search terms

- delete timeline items
- delete clips keep tracks
- non-ripple timeline delete
- delete items by frame range
- delete clips on one track
- overlap contained covering delete
- clear timeline clips

## What it does

Delete timeline items without deleting tracks and rippling the timeline.

## Do not use when

Do not run a wide delete without a project checkpoint, explicit scope, and `--force`. Omitting both frame bounds can delete every item in the selected track/type scope.

## Preflight and readback

Before execution, checkpoint/save the project; inspect the exact target timeline, track inventories, linked clips, item bounds, FPS/start frame, and intended one- or two-sided range. Prefer `--dry-run`, then independently enumerate all matching items.
If a named timeline was targeted, remember that it remains current.

## Public arguments and options

- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--track-type` (optional, default: `"all"`) — video, audio, subtitle, or all
- `--track-index/--track` (optional) — Only delete items on this track index
- `--start-frame` (optional) — Record-domain range start
- `--end-frame` (optional) — Record-domain range end
- `--match` (optional, default: `"overlap"`) — overlap, contained, or covering
- `--allow-empty` (optional, default: `false`) — Return ok when no items match
- `--force` (optional, default: `false`) — Required for wide deletes without a frame range

## Boundaries and gotchas

- `--timeline NAME` switches that project timeline current before deletion.
- `--track-index` and `--track` are aliases.
- Track index must be 1 or greater.
- Dry-run range parsing uses fixed 24 fps and start frame 0.
- When both bounds exist, end must resolve strictly after start.
- `covering` selects items spanning the whole two-sided range, or covering the supplied one-sided boundary.
- For `all`, out-of-range indices are skipped independently by type.
- The command does not explicitly expand linked item groups; selection is based on the requested filters.
- Readback verifies absence of all items matching the filter, not identity of only the preselected objects.
- It does not verify gap positions, ripple movement, linked-item effects, track count preservation, or visual/audio output beyond filtered absence.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline items delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
