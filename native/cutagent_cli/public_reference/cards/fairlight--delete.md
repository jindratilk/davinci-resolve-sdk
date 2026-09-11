# `fairlight delete`

Syntax: `cutagent fairlight delete INDEX [--force]`

## Search terms

- delete Fairlight audio track
- remove audio track
- delete A3
- get rid of empty sound track
- remove dialogue track from timeline
- delete entire audio lane
- remove unused audio track
- delete track and its clips
- reduce audio track count
- erase audio channel strip
- permanently remove timeline audio track

## What it does

Delete an audio track.

## Do not use when

Use `fairlight clip delete` when deleting selected audio timeline items while keeping their track.
Use `fairlight mute`, `fairlight disable`, or the corresponding track state command when the lane should remain available but inaudible/inactive. Deleting loses the track's position and settings instead of toggling state.
Use `fairlight rename` when only the label is unwanted, or `fairlight ensure-tracks`/`fairlight add` when changing available layout without removing an existing populated lane.
Do not use this command as a bus/FlexBus delete, channel-mapping edit, mixer-strip reset, or media deletion. The target is an audio timeline track index.
Do not delete by a remembered index after any track insertion/deletion. Re-list tracks immediately before mutation; indices are positional and later tracks shift when an earlier one is removed.

## Preflight and readback

Record track name, format, clip count/items, enabled/locked state, effects, automation, routing/bus membership and every following track's identity. Move or export anything that must survive. Prefer testing/removing an empty final track; deleting a populated track is irreversible at the command layer.
Afterward, require the audio track count to be one lower, but also re-list every remaining track and compare names, formats and item counts. Audition/rerender when routing or mixer layout mattered.

## Public arguments and options

- `INDEX` (required) — Audio track index
- `--force` (optional, default: `false`) — Required for live audio track deletion

## Boundaries and gotchas

- Indexing is 1-based and audio-only.
- Dry-run validates only `index >= 1`.
- `fairlight delete 99` without `--force` reports the missing `--force`, not whether A99 exists.
- There is no delete-by-name or `--timeline` selector.
- It does not inspect or block on track lock, enable state, record arm, inserts, automation, sends or bus routing.
- It does not prove the intended name/track ID disappeared, that a particular set of clips vanished, or that remaining track metadata/routing stayed attached correctly.
- The command does not explicitly restore selection, active track, playhead, Fairlight mixer focus or page.

## DaVinci Resolve editions

Free was not independently exercised for this card.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight delete --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
