# `timeline items set-duration`

Syntax: `cutagent timeline items set-duration [--timeline VALUE] [--batch-file VALUE] [--item-id VALUE] [--track-type VALUE] [--track-index VALUE] [--start-frame VALUE] [--current-end-frame VALUE] [--name VALUE] [--duration VALUE] [--end-frame VALUE] [--allow-overlap] [--no-source-bounds]`

## Search terms

- set timeline item duration
- change clip end frame
- batch timeline durations
- move clip start and end
- source bounds duration guard
- allow overlapping timeline items

## What it does

Set a timeline item duration.

## Do not use when

Do not use it for ripple trims, source in/out edits, speed changes, linked A/V retiming, transition-aware editing, or moving neighboring clips. `--allow-overlap` merely disables collision protection; it does not ripple or repair the edit.

## Preflight and readback

Before execution, save and checkpoint the project; inspect the active project/timeline, FPS/start frame, target track, exact item identity, current start/end, next-item gap, links, transitions, and available source tail.

## Public arguments and options

- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--batch-file` (optional)
- `--item-id` (optional)
- `--track-type` (optional, default: `"video"`) — video, audio, or subtitle
- `--track-index/--track` (optional, default: `1`) — Track index for selector
- `--start-frame` (optional) — Current item start in record-domain frames/time
- `--current-end-frame` (optional) — Current item end for stricter selection
- `--name` (optional) — Current timeline item name for stricter selection
- `--duration` (optional) — New item duration: frames, seconds, or timecode
- `--end-frame/--target-end-frame` (optional) — New item end in record-domain frames/time
- `--allow-overlap` (optional, default: `false`) — Allow the new duration to overlap the next item on the same track
- `--no-source-bounds` (optional, default: `false`) — Do not reject API-reported source/right-trim overrun before DB write

## Boundaries and gotchas

- `--timeline NAME` switches that project timeline current.
- Single mode and batch mode are mutually exclusive.
- In single mode, provide exactly one of `--duration` or `--end-frame`/`--target-end-frame`.
- `--end-frame` and `--target-end-frame` are aliases.
- `--track-index` and `--track` are aliases.
- Track index defaults to 1 and must be at least 1.
- `--item-id` cannot be combined with `--start-frame`, `--current-end-frame`, or `--name`.
- Without an item id, at least `--start-frame` or `--name` is required.
- Descriptor selection scans only the requested track.
- `--duration` is a relative positive length.
- `--target-end-frame` is a record-domain endpoint and must resolve after the current or requested start.
- `--no-source-bounds` disables that guard and can produce a range DaVinci Resolve cannot use correctly.
- Without `--allow-overlap`, a new end cannot cross the next same-track item.
- `--allow-overlap` bypasses only the collision guard; it does not ripple, move, trim, or relink any other item.
- Single mode changes duration/end but does not move the item start.
- Audio-only duration changes are blocked for linked A/V companions by the normal CLI path.
- Every batch entry must be a JSON object, and the array must be nonempty.
- All batch entries must resolve to that one timeline.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent timeline items set-duration --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
