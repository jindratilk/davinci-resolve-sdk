# `fairlight clip delete`

Syntax: `cutagent fairlight clip delete [--timeline VALUE] [--track VALUE] [--start-frame VALUE] [--end-frame VALUE] [--match VALUE] [--allow-empty] [--force]`

## Search terms

- delete audio clips from timeline
- remove Fairlight clip without ripple
- clear audio items in a frame range
- delete sound clips but keep tracks
- remove audio from one track
- delete all audio clips in region
- non-ripple audio delete
- leave a gap after deleting audio
- clear Fairlight timeline range
- remove contained audio items
- delete audio clips overlapping selection
- empty an audio track without deleting track

## What it does

Delete Fairlight audio clips without deleting tracks and rippling the timeline.

## Do not use when

Use a ripple-delete command when later material must close the gap. `fairlight clip delete` always asks for non-ripple behavior.
Use `fairlight clip trim` to shorten a clip while preserving part of it, `fairlight clip split` to create edit points, or `fairlight clip move`/`nudge` to reposition it. An overlap window does not cut at the boundaries; it removes each entire matching TimelineItem.
Use timeline track deletion only when the track container itself should disappear. This command removes audio items but preserves the audio track, its index, name, mixer configuration and items outside the filter.
Do not use this route to delete Media Pool assets; use `media delete` for source items. Deleting a timeline occurrence does not remove its Media Pool item or source file.
Do not assume an audio-only candidate list guarantees safe behavior for linked A/V clips. Inspect links and use an explicitly link-aware workflow when video must be protected.

## Preflight and readback

Before deletion, list audio items with track indices and absolute start/end frames. Convert the user's intended range to the timeline's record domain and choose `overlap`, `contained` or `covering` deliberately. Use a track index whenever possible.
For a wide delete, require explicit confirmation before adding `--force`. If using `--timeline`, record the original active timeline if it must be restored later.
Verify the target track still exists. Use `--allow-empty` for intentionally idempotent cleanup retries.

## Public arguments and options

- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--track/--track-index` (optional) — Only delete audio items on this track index
- `--start-frame` (optional) — Record-domain range start
- `--end-frame` (optional) — Record-domain range end
- `--match` (optional, default: `"overlap"`) — overlap, contained, or covering
- `--allow-empty` (optional, default: `false`) — Return ok when no audio items match
- `--force` (optional, default: `false`) — Required for wide deletes without a frame range

## Boundaries and gotchas

- Selection is range-based, not name- or item-ID-based.
- `overlap` deletes the whole item even when the window intersects only one frame in its middle.
- `contained` means the whole item lies inside the window; it is not a request to delete only the contained portion of a longer item.
- `covering` reverses the relationship: the item must contain the whole requested window.
- Their meaning changes with the predicate, so do not omit a boundary casually.
- No frame range requires `--force` even when `--track` is present.
- `--track 2 --force` deletes every audio item on A2; `--force` with no track index deletes across all audio tracks.
- `--timeline` performs an exact timeline-name switch and does not restore the previously active timeline after deletion.
- The command enumerates audio tracks only.

## Stable public error codes

- `API_CALL_FAILED`
- `CONFIRMATION_REQUIRED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight clip delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
