# `multicam reorder-angles`

Syntax: `cutagent multicam reorder-angles [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--angle-order VALUE] [--angle-order-json VALUE] [--rename-tracks] [--include-audio] [--strict]`

## Search terms

- reorder multicam angles
- reorder VideoTrackVec
- reorder AudioTrackVec
- rename multicam angle tracks
- partial angle reorder
- strict angle order
- multicam angle-order JSON

## What it does

Reorder multicam angles.

## Do not use when

Do not use ambiguous basenames/clip names. A value matching multiple tracks is rejected; use an exact full media path when possible.
Do not use default `--include-audio` blindly when isolated audio tracks have different media names/paths from video angles. The same requested values must resolve the audio order too.
Do not use `--partial` unless intentionally moving a subset to the front while preserving unmatched tracks afterward.
Do not accept default track renaming if custom angle names must remain. Pass `--no-rename-tracks`.
Confirm DaVinci Resolve's one-based angle menu, audio pairing, playback, and render.

## Preflight and readback

Before execution, archive/export the project, inspect the multicam, capture media/sequence IDs, current video/audio order, custom track names, selector state, and source paths. Resolve duplicate basenames.
Run dry-run with an exact selector and full paths.
Require expected video order, optional audio order, preserved video/audio track and item counts, and expected names.
Then reopen/inspect the same project and multicam in DaVinci Resolve, verify the angle selector/menu order and audio correspondence, and render/play representative switches.

## Public arguments and options

- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--angle-order` (optional, repeatable) — Repeatable desired angle order value; matches media path, basename, or clip name
- `--angle-order-json` (optional) — Path to a JSON array or object with angle_order[] values
- `--rename-tracks/--no-rename-tracks` (optional, default: `true`)
- `--include-audio/--video-only` (optional, default: `true`) — Reorder audio angle tracks alongside video tracks when available
- `--strict/--partial` (optional, default: `true`) — Require the requested order to cover every matching track exactly once

## Boundaries and gotchas

- Case variants are not deduplicated by the exact-string duplicate check and can later fail because the first match consumes the track.
- A requested value with multiple matches is rejected as ambiguous.
- `--strict` is default and requires every video track, and included audio track, exactly once.
- `--partial` appends unmatched rows after the requested rows in their existing order.
- `--include-audio` is default.
- If audio tracks exist, the same requested values must match them; different isolated audio names can make the plan fail.
- `--video-only` leaves audio relation order and names unchanged.
- `--rename-tracks` is default and renames both planned video/audio rows to `Angle 1`, `Angle 2`, etc.
- `--no-rename-tracks` preserves current user-defined names.
- There is no command-specific `--force` or confirmation flag.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent multicam reorder-angles --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
