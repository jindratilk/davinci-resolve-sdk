# `timeline marker add`

Syntax: `cutagent timeline marker add POSITION [--color VALUE] [--name VALUE] [--note VALUE] [--duration VALUE]`

## Search terms

- add timeline marker
- leave edit note at timecode
- place colored marker
- flag a frame for review
- annotate timeline position
- mark audio fix location
- add duration marker
- create review cue
- drop marker one second in

## What it does

Add a marker at a position.

## Do not use when

Do not use it to define an in/out range for playback or rendering (`timeline mark set`). Do not use it for a marker attached to a source clip or timeline item. Use `timeline marker batch` when adding several markers, ranges, collision-aware annotations, or targeting a non-active timeline by name. Use a clip comment/metadata command when the note must follow a clip after it moves; this marker remains at a timeline position.

## Preflight and readback

Choose an unoccupied position and an exact DaVinci Resolve marker color; decide whether the user's reference is relative or absolute.

## Public arguments and options

- `POSITION` (required) — Position (timecode, seconds, frames)
- `--color` (optional, default: `"Blue"`) — Marker color
- `--name` (optional, default: `""`) — Marker name
- `--note` (optional, default: `""`) — Marker note
- `--duration` (optional, default: `1`) — Duration in frames

## Boundaries and gotchas

- Only one marker can occupy a timeline frame.

## Examples

- `cutagent timeline marker add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
