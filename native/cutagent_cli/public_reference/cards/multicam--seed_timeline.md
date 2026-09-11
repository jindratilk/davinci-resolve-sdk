# `multicam seed-timeline`

Syntax: `cutagent multicam seed-timeline [--multicam-name VALUE] [--media-id VALUE] [--folder VALUE] [--timeline VALUE] [--record-frame VALUE] [--absolute-record-frame VALUE] [--require-empty] [--reset-first] [--force]`

## Search terms

- append multicam to V1
- reset timeline before multicam
- require empty target timeline
- multicam record frame
- absolute record frame
- repair multicam MediaRef

## What it does

Append a multicam clip to V1 of a target timeline.

## Do not use when

The target timeline and multicam Media Pool item must already exist.
Do not use both `--record-frame` and `--absolute-record-frame`, or both `--require-empty` and `--reset-first`.
Do not expect the default mode to append into a populated timeline.
Do not use `--reset-first` unless clearing every existing video/audio timeline item is intended. It preserves tracks but deletes their item relationships, links, compositions, and items before the append.
A later failure can leave the timeline cleared or leave an appended item awaiting repair.

## Preflight and readback

Before execution, export/archive the project; record the exact project, timeline, multicam name/media ID/folder, timeline start frame, current video/audio track and item counts, and intended insertion frame.
Use `--force` only after reviewing that destructive scope.

## Public arguments and options

- `--multicam-name` (optional)
- `--media-id` (optional)
- `--folder` (optional) — Optional Media Pool folder path to disambiguate duplicate multicam names
- `--timeline` (optional) — Target timeline name; defaults to the active timeline
- `--record-frame` (optional) — Record-domain frame, timecode, seconds, or frames offset for the V1 append
- `--absolute-record-frame` (optional) — Exact DaVinci Resolve API recordFrame; no timeline-start offset is applied
- `--require-empty` (optional, default: `false`) — Fail unless the target timeline has no video/audio items
- `--reset-first` (optional, default: `false`) — Clear video/audio timeline items before appending, preserving tracks
- `--force/-f` (optional, default: `false`) — Confirm reset-first timeline item deletion

## Boundaries and gotchas

- At least one of `--multicam-name` or `--media-id` is required by target resolution.
- If both selectors are supplied, the resolved item must satisfy the requested identity.
- `--folder` disambiguates name matches using an exact or suffix folder-path match.
- `--timeline` is an exact name; omission selects the current timeline.
- `--record-frame` is parsed as a timeline-relative frame/time/seconds reference and has the timeline start added.
- `--require-empty` and `--reset-first` are mutually exclusive.
- The default behavior also rejects a nonempty target timeline unless `--reset-first` is present.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent multicam seed-timeline --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
