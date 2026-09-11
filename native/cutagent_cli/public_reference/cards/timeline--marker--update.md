# `timeline marker update`

Syntax: `cutagent timeline marker update --frame VALUE [--position VALUE] [--color VALUE] [--name VALUE] [--note VALUE] [--duration VALUE]`

## Search terms

- move marker to another frame
- edit marker color
- rename timeline marker
- change marker note
- change marker duration
- revise review cue
- replace marker safely

## What it does

Update one exact marker with rollback on replacement failure.

## Do not use when

Use `timeline marker add` for a new marker and `timeline marker delete` for removal. Do not use it when the target marker has not been identified by an exact frame from a current marker listing.

## Preflight and readback

Run `timeline marker list` first and retain the complete target row, including both timeline-relative and record frames. Choose an unoccupied destination when moving the marker.

## Public arguments and options

- `--frame` (required) — Exact timeline or record frame of the marker to update
- `--position` (optional) — Optional new position (timecode, seconds, frames)
- `--color` (optional) — Optional new marker color
- `--name` (optional) — Optional new marker name
- `--note` (optional) — Optional new marker note
- `--duration` (optional) — Optional new duration in frames

## Boundaries and gotchas

- `--frame` identifies the existing marker.
- `--position` uses the same mixed position syntax as marker add: seconds and frame suffixes are relative to timeline start, while timecodes may resolve as relative or absolute based on the timeline start.

## Examples

- `cutagent timeline marker update --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
