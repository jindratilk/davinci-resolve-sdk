# `fairlight track-order move`

Syntax: `cutagent fairlight track-order move INDEX --to VALUE`

## Search terms

- reorder Fairlight tracks
- move audio track up
- move A3 to A1
- put music track below dialogue
- change audio track order
- move track to top
- send Fairlight track to bottom
- rearrange audio lanes
- reorder mixer track rows
- change track index
- move surround track above stereo
- organize Fairlight track stack

## What it does

Move an existing Fairlight audio track in DaVinci Resolve.

## Do not use when

Use a Fairlight clip move/nudge command when one clip should move to another audio track or time.
Use `fairlight add` when the user wants a new track at an insertion position, `fairlight delete` to remove a track, and `fairlight track duplicate` to create a copy. Reordering neither creates nor deletes track content.
Use `fairlight track-format set` when only the channel layout should change. Moving a track preserves its subtype.
Do not describe this as a simple two-track swap. Moving A1 to A3 produces `[old A2, old A3, old A1]`; all intervening tracks shift.
Do not use it to reorder video tracks, buses, VCAs, Fairlight folder membership or mixer routing.

## Preflight and readback

Resolve the intended track by stable identity, not only a stale number. Save/checkpoint the test project and run the exact source/destination with `--dry-run`.
If the timeline contains processing, automation, routing, buses, sends or plugins, capture those states and an audio render before moving.
Run `fairlight tracks` again and confirm names, formats, clip counts and stable UUIDs at every new index. Verify that the moved track's clips remain at the same record positions. Re-resolve all later commands that use numeric track indices.
For processed projects, audition/render and check fader, pan, EQ, dynamics, plugin, send and routing ownership after reopen.

## Public arguments and options

- `INDEX` (required) — Audio track index to move
- `--to` (required) — Destination audio track index

## Boundaries and gotchas

- It rewrites the relation indices for every audio track, not only the moved row.
- Do not use it as a read-only identity check.

## Examples

- `cutagent fairlight track-order move --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
